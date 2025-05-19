"""
Rule evaluation and action execution tasks.

This module defines Celery tasks for evaluating sensor data against 
rules and executing actions when conditions are met.
"""
import logging
import redis
import json
from datetime import datetime
from typing import Dict, Any
from celery_app import app
from app.core.tasks.common import TaskMetrics
from app.core.env_settings import env

logger = logging.getLogger(__name__)

# Connect to Redis for persistent rule state with proper error handling
redis_client = None
try:
    redis_client = redis.Redis.from_url(env.REDIS_URL, socket_timeout=2.0)
    redis_client.ping()  # Test connection
    logger.info("Connected to Redis for rule state management")
except Exception as e:
    logger.error(f"Redis connection error: {e} - Using local state fallback")
    redis_client = None

# Local fallback state if Redis is unavailable
_local_rule_states = {}

def get_rule_state(task_id: str) -> bool:
    """
    Get rule state with Redis fallback to local cache.
    
    Args:
        task_id: ID of the rule/task
        
    Returns:
        Current state of the rule (True for triggered, False for not triggered)
    """
    if redis_client:
        try:
            state = redis_client.get(f"r:{task_id}:state")
            return state == b"1"
        except Exception as e:
            logger.warning(f"Redis read error: {e}")
    
    # Fallback to local state
    return _local_rule_states.get(task_id, False)

def set_rule_state(task_id: str, state: bool) -> None:
    """
    Set rule state with Redis fallback to local cache.
    
    Args:
        task_id: ID of the rule/task
        state: New state (True for triggered, False for not triggered)
    """
    # Update local cache regardless
    _local_rule_states[task_id] = state
    
    if redis_client:
        try:
            # Store state and timestamps in a pipeline for efficiency
            with redis_client.pipeline() as pipe:
                pipe.set(f"r:{task_id}:state", "1" if state else "0")
                timestamp = datetime.now().isoformat()
                if state:
                    pipe.set(f"r:{task_id}:triggered", timestamp)
                else:
                    pipe.set(f"r:{task_id}:cleared", timestamp)
                pipe.execute()
        except Exception as e:
            logger.warning(f"Redis write error: {e}")

def _evaluate_condition(value: float, operator: str, threshold: float) -> bool:
    """
    Evaluate a condition based on the operator and threshold.
    
    Args:
        value: The value to evaluate
        operator: Comparison operator (>, <, >=, <=, ==, !=)
        threshold: Threshold value for comparison
        
    Returns:
        Result of the comparison
    """
    operators = {
        '>': lambda a, b: a > b,
        '<': lambda a, b: a < b,
        '>=': lambda a, b: a >= b,
        '<=': lambda a, b: a <= b,
        '==': lambda a, b: a == b,
        '!=': lambda a, b: a != b
    }
    
    op_func = operators.get(operator)
    if not op_func:
        logger.error(f"Unknown operator: {operator}")
        return False
        
    return op_func(value, threshold)

@app.task
def evaluate_rules(source: str, data: Dict[str, float]) -> Dict[str, Any]:
    """
    Evaluate a data point against all tasks that use this source.
    
    Args:
        source: The source identifier of the data
        data: Dictionary of data fields with their values
        
    Returns:
        Dictionary with evaluation results
    """
    with TaskMetrics(f"evaluate_rules:{source}") as metrics:
        try:
            # Get configuration
            from app.core.config import config_manager
            config = config_manager.get_config()
            
            # Filter tasks for this source (optimization)
            tasks = [task for task in config.tasks if task.source == source]
            
            if not tasks:
                logger.debug(f"No rules found for source {source}")
                return {
                    "status": "success", 
                    "message": "No rules for this source",
                    "source": source
                }
            
            logger.debug(f"Found {len(tasks)} rules for source {source}")
            metrics.set("rules_total", len(tasks))
            
            # Track processed rules
            processed = 0
            triggered = 0
            cleared = 0
            
            # Process each task
            for task in tasks:
                try:
                    # Skip if the required field isn't in the data
                    if task.field not in data:
                        logger.debug(f"Field '{task.field}' not in data for rule '{task.name}'")
                        continue
                    
                    # Get the current value and evaluate the condition
                    value = data[task.field]
                    condition_met = _evaluate_condition(value, task.operator, task.value)
                    previously_triggered = get_rule_state(task.id)
                    
                    processed += 1
                    metrics.increment("processed")
                    
                    # Handle state transitions with proper logging
                    if condition_met and not previously_triggered:
                        # NOT TRIGGERED -> TRIGGERED
                        logger.info(f"Rule TRIGGERED: {task.name} ({task.field} {task.operator} {task.value}, value={value})")
                        set_rule_state(task.id, True)
                        triggered += 1
                        metrics.increment("triggered")
                        
                        # Execute actions for this task
                        for action in task.actions:
                            action_data = action.model_dump()
                            execute_action.delay(task.id, task.name, action_data, data)
                            
                    elif not condition_met and previously_triggered:
                        # TRIGGERED -> NOT TRIGGERED
                        logger.info(f"Rule CLEARED: {task.name} (value={value})")
                        set_rule_state(task.id, False)
                        cleared += 1
                        metrics.increment("cleared")
                        
                except Exception as e:
                    logger.error(f"Error processing rule '{task.name}': {e}")
                    metrics.increment("errors")
                    
            return {
                "status": "success",
                "source": source,
                "rules_total": len(tasks),
                "rules_processed": processed,
                "rules_triggered": triggered,
                "rules_cleared": cleared,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error evaluating rules for {source}: {e}")
            metrics.increment("errors")
            return {
                "status": "error",
                "message": str(e),
                "source": source
            }

@app.task
def execute_action(task_id: str, task_name: str, action_data: Dict[str, Any], 
                 sensor_data: Dict[str, float]) -> Dict[str, Any]:
    """
    Execute a rule action with optimized error handling and retries.
    
    Args:
        task_id: ID of the rule/task
        task_name: Name of the rule/task
        action_data: Action configuration data
        sensor_data: Sensor data that triggered the rule
        
    Returns:
        Dictionary with action execution results
    """
    action_type = action_data.get("type", "unknown")
    
    with TaskMetrics(f"execute_action:{action_type}") as metrics:
        try:
            logger.debug(f"Executing {action_type} action for rule '{task_name}'")
            
            result = {"status": "unknown", "action_type": action_type}
            
            if action_type == "io":
                result = _execute_io_action(action_data)
            elif action_type == "log":
                result = _execute_log_action(action_data, task_name, sensor_data)
            elif action_type == "reboot":
                result = _execute_reboot_action()
            else:
                result = {"status": "error", "message": f"Unknown action type: {action_type}"}
                
            return result
            
        except Exception as e:
            logger.error(f"Error executing {action_type} action for rule '{task_name}': {e}")
            metrics.increment("errors")
            return {
                "status": "error", 
                "message": str(e),
                "action_type": action_type
            }

def _execute_io_action(action_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute an IO action (relay control) using Celery relay tasks.
    
    Args:
        action_data: Action configuration data
        
    Returns:
        Dictionary with action execution results
    """
    target = action_data.get("target")
    state = action_data.get("state", "").lower() if action_data.get("state") else ""
    
    if not target or not state:
        return {"status": "error", "message": "Missing target or state parameters"}
    
    try:
        result = {"status": "success", "target": target, "action": state}
        
        if state == "on":
            # Turn relay on
            from app.core.tasks.relay_tasks import set_relay_state
            task = set_relay_state.delay(target, True)
            result["task_id"] = task.id
            logger.info(f"IO ACTION: Turning relay {target} ON")
            
        elif state == "off":
            # Turn relay off
            from app.core.tasks.relay_tasks import set_relay_state
            task = set_relay_state.delay(target, False) 
            result["task_id"] = task.id
            logger.info(f"IO ACTION: Turning relay {target} OFF")
            
        elif state == "pulse":
            # Get pulse time from config
            pulse_time = 5  # Default
            from app.core.config import config_manager
            config = config_manager.get_config()
            for relay in config.relays:
                if relay.id == target:
                    pulse_time = relay.pulse_time
                    break
                    
            # Pulse the relay
            from app.core.tasks.relay_tasks import pulse_relay
            task = pulse_relay.delay(target, pulse_time)
            result["task_id"] = task.id
            result["pulse_time"] = pulse_time
            logger.info(f"IO ACTION: Pulsing relay {target} for {pulse_time}s")
            
        else:
            return {"status": "error", "message": f"Unknown IO state: {state}"}
            
        return result
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _execute_log_action(action_data: Dict[str, Any], task_name: str, 
                      sensor_data: Dict[str, float]) -> Dict[str, Any]:
    """
    Execute a log action with better formatting and persistence.
    
    Args:
        action_data: Action configuration data
        task_name: Name of the rule/task
        sensor_data: Sensor data that triggered the rule
        
    Returns:
        Dictionary with action execution results
    """
    # Get message or use default
    message = action_data.get("message") or f"Alert from rule '{task_name}'"
    
    # Format data more cleanly
    data_str = ", ".join([f"{k}={v}" for k, v in sensor_data.items()])
    
    # Log the message
    logger.info(f"RULE ALERT [{task_name}]: {message} | Data: {data_str}")
    
    # Store log in Redis if available
    if redis_client:
        try:
            # Use shorter key with timestamp
            timestamp = int(datetime.now().timestamp())
            log_key = f"log:{task_name}:{timestamp}"
            
            log_data = {
                "message": message,
                "data": sensor_data,
                "timestamp": datetime.now().isoformat()
            }
            
            redis_client.set(log_key, json.dumps(log_data))
            redis_client.expire(log_key, 604800)  # 7 days
        except Exception as e:
            logger.warning(f"Redis log storage error: {e}")
    
    return {
        "status": "success",
        "action": "log",
        "message": message,
        "logged_at": datetime.now().isoformat()
    }

def _execute_reboot_action() -> Dict[str, Any]:
    """
    Execute a reboot action with safety checks.
    
    Returns:
        Dictionary with action execution results
    """
    logger.warning("SYSTEM REBOOT requested by rule action")
    
    # Check if already scheduled
    reboot_scheduled = False
    reboot_key = "system:reboot"
    
    if redis_client:
        try:
            reboot_scheduled = bool(redis_client.exists(reboot_key))
            if not reboot_scheduled:
                redis_client.set(reboot_key, "1")
                redis_client.expire(reboot_key, 60)  # Expire after 1 minute
        except Exception as e:
            logger.error(f"Redis error in reboot action: {e}")
    
    if not reboot_scheduled:
        try:
            with open('/dev/watchdog', 'w') as wdt:
                wdt.write('X')
            return {"status": "success", "message": "System reboot initiated"}
        except Exception as e:
            return {"status": "error", "message": f"Reboot failed: {e}"}
    else:
        return {"status": "info", "message": "System reboot already scheduled"}

@app.task
def get_rule_status() -> Dict[str, Any]:
    """
    Get the status of all rules.
    
    Returns:
        Dictionary mapping rule IDs to their current status.
    """
    with TaskMetrics("get_rule_status") as metrics:
        try:
            # Get configuration
            from app.core.config import config_manager
            config = config_manager.get_config()
            tasks_list = config.tasks
            
            # Initialize result
            result = {}
            
            # Process all tasks
            for task in tasks_list:
                task_id = task.id
                metrics.increment("rules_total")
                
                # Build task info
                task_info = {
                    "name": task.name,
                    "source": task.source,
                    "field": task.field,
                    "operator": task.operator,
                    "value": task.value,
                    "actions_count": len(task.actions),
                    "triggered": get_rule_state(task_id)
                }
                
                # Add timestamps if available (from Redis)
                if redis_client:
                    # Get triggered timestamp
                    triggered_at = None
                    try:
                        triggered_at = redis_client.get(f"r:{task_id}:triggered")
                    except Exception:
                        pass
                        
                    if triggered_at:
                        task_info["last_triggered"] = triggered_at.decode('utf-8')
                        
                    # Get cleared timestamp
                    cleared_at = None
                    try:
                        cleared_at = redis_client.get(f"r:{task_id}:cleared")
                    except Exception:
                        pass
                        
                    if cleared_at:
                        task_info["last_cleared"] = cleared_at.decode('utf-8')
                
                # Add to result
                result[task_id] = task_info
                metrics.increment("rules_processed")
            
            # Add summary info
            triggered_count = sum(1 for info in result.values() 
                                if isinstance(info, dict) and info.get("triggered", False))
            
            metrics.set("triggered_rules", triggered_count)
            
            return result
        except Exception as e:
            logger.error(f"Error getting rule status: {e}")
            metrics.increment("errors")
            return {"error": str(e)}