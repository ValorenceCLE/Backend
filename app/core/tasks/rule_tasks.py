"""
Rule evaluation tasks.

This module defines Celery tasks for evaluating sensor data against 
defined rules and executing actions.
"""
import logging
import redis
from datetime import datetime, timezone
from typing import Dict, Any, List
from celery_app import app
from app.utils.validator import load_config, Task, TaskAction
from app.core.tasks.relay_tasks import set_relay_state, pulse_relay

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Ensure this is INFO level

# Connect to Redis for persistent rule state
redis_client = redis.Redis.from_url('redis://redis:6379/0')

def get_rule_state(task_id):
    """Get the current state of a rule from Redis"""
    try:
        state = redis_client.get(f"rule_state:{task_id}")
        return state == b"1"
    except Exception as e:
        logger.error(f"Error reading rule state from Redis: {e}")
        return False

def set_rule_state(task_id, state):
    """Set the state of a rule in Redis"""
    try:
        redis_client.set(f"rule_state:{task_id}", "1" if state else "0")
        # Also set timestamp for when state last changed
        if state:
            redis_client.set(f"rule_triggered_at:{task_id}", datetime.now().isoformat())
        else:
            redis_client.set(f"rule_cleared_at:{task_id}", datetime.now().isoformat())
    except Exception as e:
        logger.error(f"Error setting rule state in Redis: {e}")

@app.task(bind=True)
def evaluate_rules(self, source: str, data: Dict[str, float]):
    """
    Evaluate a data point against all tasks that use this source.
    """
    # Log at INFO level so it shows in the logs
    logger.info(f"RULE EVALUATION: Source={source}, Data={data}")
    
    try:
        # Load configuration to get tasks
        config = load_config("app/config/custom_config.json")
        
        # Build source-to-tasks mapping
        source_to_tasks = {}
        for task_id, task in config.tasks.items():
            if task.source not in source_to_tasks:
                source_to_tasks[task.source] = []
            source_to_tasks[task.source].append((task_id, task))
        
        # Skip if no tasks for this source
        if source not in source_to_tasks:
            logger.info(f"No tasks found for source {source}")
            return True
        
        task_items = source_to_tasks[source]
        logger.info(f"Found {len(task_items)} tasks for source {source}")
        
        # Process each task - simplify by doing it directly
        for task_id, task in task_items:
            # Skip if the field doesn't exist in the data
            if task.field not in data:
                logger.warning(f"Field '{task.field}' not in data for task '{task.name}' ({task_id})")
                continue
            
            # Evaluate the condition
            value = data[task.field]
            condition_met = _evaluate_condition(value, task.operator, task.value)
            previously_triggered = get_rule_state(task_id)
            
            logger.info(f"RULE CHECK: Task '{task.name}' ({task_id}): {value} {task.operator} {task.value} = {condition_met}, previously_triggered={previously_triggered}")
            
            # Handle state transitions
            if condition_met and not previously_triggered:
                # NOT TRIGGERED -> TRIGGERED
                logger.info(f"RULE TRIGGERED: Task '{task.name}' ({task_id})")
                set_rule_state(task_id, True)
                
                # Execute actions for the task
                for action in task.actions:
                    execute_action.delay(task_id, task.name, action.model_dump(), data)
                    
            elif not condition_met and previously_triggered:
                # TRIGGERED -> NOT TRIGGERED
                logger.info(f"RULE CLEARED: Task '{task.name}' ({task_id})")
                set_rule_state(task_id, False)
                
        return True
    except Exception as e:
        logger.error(f"Error evaluating rules: {e}")
        return False

def _evaluate_condition(value: float, operator: str, threshold: float) -> bool:
    """
    Evaluate a condition based on the operator and threshold.
    """
    try:
        if operator == '>':
            return value > threshold
        elif operator == '<':
            return value < threshold
        elif operator == '>=':
            return value >= threshold
        elif operator == '<=':
            return value <= threshold
        elif operator == '==':
            return value == threshold
        elif operator == '!=':
            return value != threshold
        else:
            logger.error(f"Unknown operator: {operator}")
            return False
    except Exception as e:
        logger.error(f"Error evaluating condition: {e}")
        return False

@app.task(bind=True)
def execute_action(self, task_id: str, task_name: str, action_data: Dict, data: Dict):
    """
    Execute a single action as a separate task.
    """
    try:
        # Convert action_data back to TaskAction
        action = TaskAction(**action_data)
        
        logger.info(f"EXECUTING ACTION: {action.type} for task '{task_name}' ({task_id})")
        
        if action.type == "io":
            _execute_io_action(action)
        elif action.type == "log":
            _execute_log_action(action, task_name, data)
        elif action.type == "reboot":
            _execute_reboot_action()
        else:
            logger.error(f"Unknown action type: {action.type}")
    except Exception as e:
        logger.error(f"Error executing action: {e}")

def _execute_io_action(action: TaskAction):
    """
    Execute an IO action (relay control) using Celery relay tasks.
    """
    if not action.target or not action.state:
        logger.error("IO action missing target or state")
        return
    
    target = action.target
    state = action.state.lower()
    
    try:
        if state == "on":
            # Use relay task instead of direct controller
            set_relay_state.delay(target, True)
            logger.info(f"IO ACTION: Turning relay {target} ON")
        elif state == "off":
            set_relay_state.delay(target, False)
            logger.info(f"IO ACTION: Turning relay {target} OFF")
        elif state == "pulse":
            # Default to 5 seconds if config lookup fails
            pulse_time = 5
            try:
                config = load_config("app/config/custom_config.json")
                relay_config = next((r for r in config.relays if r.id == target), None)
                if relay_config:
                    pulse_time = relay_config.pulse_time
            except Exception as e:
                logger.error(f"Error getting pulse time: {e}")
                
            pulse_relay.delay(target, pulse_time)
            logger.info(f"IO ACTION: Pulsing relay {target} for {pulse_time}s")
        else:
            logger.error(f"Unknown IO state: {state}")
    except Exception as e:
        logger.error(f"Error executing IO action on {target}: {e}")

def _execute_log_action(action: TaskAction, task_name: str, data: Dict[str, float]):
    """
    Execute a log action.
    """
    message = action.message or f"Alert from task '{task_name}'"
    logger.info(f"TASK ALERT: {message}")
    logger.info(f"TASK DATA: {data}")

def _execute_reboot_action():
    """
    Execute a reboot action.
    """
    logger.warning("SYSTEM REBOOT requested by task action")
    try:
        # Schedule the reboot to happen after a short delay
        import subprocess
        subprocess.Popen(["sudo", "reboot"])
    except Exception as e:
        logger.error(f"Error scheduling reboot: {e}")

@app.task(name="app.core.tasks.rule_tasks.get_rule_status")
def get_rule_status():
    """
    Get the status of all rules.
    
    This is useful for debugging and monitoring.
    """
    try:
        # Load configuration
        config = load_config("app/config/custom_config.json")
        
        # Get states from Redis
        result = {}
        for task_id, task in config.tasks.items():
            # Get current state
            triggered = get_rule_state(task_id)
            
            # Add task info
            result[task_id] = {
                "name": task.name,
                "source": task.source,
                "field": task.field,
                "operator": task.operator,
                "value": task.value,
                "triggered": triggered,
                "actions_count": len(task.actions)
            }
            
            # Add timestamps if available
            triggered_at = redis_client.get(f"rule_triggered_at:{task_id}")
            if triggered_at:
                result[task_id]["last_triggered"] = triggered_at.decode('utf-8')
                
            cleared_at = redis_client.get(f"rule_cleared_at:{task_id}")
            if cleared_at:
                result[task_id]["last_cleared"] = cleared_at.decode('utf-8')
        
        return result
    except Exception as e:
        logger.error(f"Error getting rule status: {e}")
        return {"error": str(e)}