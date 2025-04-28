"""
app/core/tasks/rule_tasks.py
Enhanced rule evaluation tasks with better state management and error handling.

This module defines Celery tasks for evaluating sensor data against 
defined rules and executing actions.
"""
import logging
import redis
import json
from datetime import datetime
from typing import Dict
from celery_app import app
from app.core.tasks.relay_tasks import set_relay_state, pulse_relay
from app.core.services.config_manager import config_manager
from app.core.env_settings import env

logger = logging.getLogger(__name__)

# Connect to Redis for persistent rule state
redis_client = redis.Redis.from_url(env.REDIS_URL)

def get_rule_state(task_id):
    """Get the current state of a rule from Redis with error handling"""
    try:
        state = redis_client.get(f"rule_state:{task_id}")
        return state == b"1"
    except Exception as e:
        logger.error(f"Error reading rule state from Redis: {e}")
        return False

def set_rule_state(task_id, state):
    """Set the state of a rule in Redis with error handling"""
    try:
        redis_client.set(f"rule_state:{task_id}", "1" if state else "0")
        # Also set timestamp for when state last changed
        if state:
            redis_client.set(f"rule_triggered_at:{task_id}", datetime.now().isoformat())
        else:
            redis_client.set(f"rule_cleared_at:{task_id}", datetime.now().isoformat())
    except Exception as e:
        logger.error(f"Error setting rule state in Redis: {e}")

@app.task(bind=True, max_retries=3)
def evaluate_rules(self, source: str, data: Dict[str, float]):
    """
    Evaluate a data point against all tasks that use this source.
    """
    logger.debug(f"RULE EVALUATION: Source={source}, Data={data}")
    
    try:
        # Get configuration using the manager
        config = config_manager.get_full_config()
        
        # Check if tasks key exists
        if "tasks" not in config:
            logger.debug("No 'tasks' key in configuration, falling back to direct loading")
            # Fall back to direct loading from file
            try:
                from app.utils.validator import load_config
                pydantic_config = load_config("app/config/custom_config.json")
                tasks_list = pydantic_config.tasks
            except Exception as e:
                logger.error(f"Failed to load tasks from file: {e}")
                return False
        else:
            tasks_list = config["tasks"]
        
        # Build source-to-tasks mapping
        source_to_tasks = {}
        for task in tasks_list:
            task_source = task["source"] if isinstance(task, dict) else task.source
            if task_source not in source_to_tasks:
                source_to_tasks[task_source] = []
            source_to_tasks[task_source].append(task)
        
        # Skip if no tasks for this source
        if source not in source_to_tasks:
            logger.debug(f"No tasks found for source {source}")
            return True
        
        task_items = source_to_tasks[source]
        logger.debug(f"Found {len(task_items)} tasks for source {source}")
        
        # Process each task
        for task in task_items:
            try:
                # Handle both dictionary and Pydantic model approaches
                if isinstance(task, dict):
                    task_id = task["id"]
                    task_name = task["name"]
                    task_field = task["field"]
                    task_operator = task["operator"]
                    task_value = task["value"]
                    task_actions = task["actions"]
                else:  # Assume Pydantic model
                    task_id = task.id
                    task_name = task.name
                    task_field = task.field
                    task_operator = task.operator
                    task_value = task.value
                    task_actions = task.actions
                
                # Skip if the field doesn't exist in the data
                if task_field not in data:
                    logger.warning(f"Field '{task_field}' not in data for task '{task_name}' ({task_id})")
                    continue
                
                # Evaluate the condition
                value = data[task_field]
                condition_met = _evaluate_condition(value, task_operator, task_value)
                previously_triggered = get_rule_state(task_id)
                
                logger.debug(f"RULE CHECK: Task '{task_name}' ({task_id}): {value} {task_operator} {task_value} = {condition_met}, previously_triggered={previously_triggered}")
                
                # Handle state transitions
                if condition_met and not previously_triggered:
                    # NOT TRIGGERED -> TRIGGERED
                    logger.info(f"RULE TRIGGERED: Task '{task_name}' ({task_id})")
                    set_rule_state(task_id, True)
                    
                    # Execute actions for the task
                    for action in task_actions:
                        # If Pydantic model, convert to dict
                        action_data = action if isinstance(action, dict) else action.model_dump()
                        execute_action.delay(task_id, task_name, action_data, data)
                        
                elif not condition_met and previously_triggered:
                    # TRIGGERED -> NOT TRIGGERED
                    logger.info(f"RULE CLEARED: Task '{task_name}' ({task_id})")
                    set_rule_state(task_id, False)
            except Exception as e:
                logger.error(f"Error processing task {task_id if 'task_id' in locals() else 'unknown'}: {e}", exc_info=True)
                
        return True
    except Exception as e:
        logger.error(f"Error evaluating rules: {e}", exc_info=True)
        self.retry(exc=e)
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

@app.task(bind=True, max_retries=3)
def execute_action(self, task_id: str, task_name: str, action_data: Dict, data: Dict):
    """
    Execute a single action as a separate task with retry logic.
    """
    try:
        # We're now receiving action_data as a dict, so we work directly with it
        action_type = action_data.get("type")
        
        logger.info(f"EXECUTING ACTION: {action_type} for task '{task_name}' ({task_id})")
        
        if action_type == "io":
            _execute_io_action(action_data)
        elif action_type == "log":
            _execute_log_action(action_data, task_name, data)
        elif action_type == "reboot":
            _execute_reboot_action()
        else:
            logger.error(f"Unknown action type: {action_type}")
    except Exception as e:
        logger.error(f"Error executing action: {e}", exc_info=True)
        self.retry(exc=e)

def _execute_io_action(action_data: Dict):
    """
    Execute an IO action (relay control) using Celery relay tasks.
    """
    target = action_data.get("target")
    state = action_data.get("state", "").lower() if action_data.get("state") else ""
    
    if not target or not state:
        logger.error("IO action missing target or state")
        return
    
    try:
        if state == "on":
            set_relay_state.delay(target, True)
            logger.info(f"IO ACTION: Turning relay {target} ON")
        elif state == "off":
            set_relay_state.delay(target, False)
            logger.info(f"IO ACTION: Turning relay {target} OFF")
        elif state == "pulse":
            # Get pulse time from config
            pulse_time = 5  # Default
            try:
                config = config_manager.get_full_config()
                if "relays" in config:
                    for relay in config["relays"]:
                        if relay.get("id") == target:
                            pulse_time = relay.get("pulse_time", 5)
                            break
            except Exception as e:
                logger.error(f"Error getting pulse time: {e}")
                
            pulse_relay.delay(target, pulse_time)
            logger.debug(f"IO ACTION: Pulsing relay {target} for {pulse_time}s")
        else:
            logger.error(f"Unknown IO state: {state}")
    except Exception as e:
        logger.error(f"Error executing IO action on {target}: {e}")

def _execute_log_action(action_data: Dict, task_name: str, data: Dict[str, float]):
    """
    Execute a log action with enhanced monitoring.
    """
    message = action_data.get("message") or f"Alert from task '{task_name}'"
    logger.info(f"TASK ALERT: {message}")
    logger.info(f"TASK DATA: {data}")
    
    # Store log action in Redis for monitoring
    try:
        log_key = f"task_log:{task_name}:{int(datetime.now().timestamp())}"
        log_data = {
            "message": message,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        redis_client.set(log_key, json.dumps(log_data))
        redis_client.expire(log_key, 604800)  # Expire after 7 days
    except Exception as e:
        logger.error(f"Failed to store log in Redis: {e}")

def _execute_reboot_action():
    """
    Execute a reboot action with safety checks.
    """
    logger.warning("SYSTEM REBOOT requested by task action")
    try:
        # Check if we're already scheduled for reboot
        reboot_key = "system_reboot_scheduled"
        if redis_client.exists(reboot_key):
            logger.info("System reboot already scheduled, skipping")
            return
        
        # Schedule the reboot
        redis_client.set(reboot_key, "1")
        redis_client.expire(reboot_key, 60)  # Expire after 1 minute
        
        import subprocess
        subprocess.Popen(["sudo", "reboot"])
    except Exception as e:
        logger.error(f"Error scheduling reboot: {e}")

@app.task(name="app.core.tasks.rule_tasks.get_rule_status")
def get_rule_status():
    """
    Get the status of all rules with enhanced error handling.
    """
    try:
        # Get config from config manager
        config = config_manager.get_full_config()
        
        # Check if tasks key exists
        if "tasks" not in config:
            logger.debug("No 'tasks' key in configuration for rule status, falling back to direct loading")
            # Fall back to direct loading from file
            try:
                from app.utils.validator import load_config
                pydantic_config = load_config("app/config/custom_config.json")
                tasks_list = pydantic_config.tasks
            except Exception as e:
                logger.error(f"Failed to load tasks from file for status: {e}")
                return {"error": "Failed to load tasks"}
        else:
            tasks_list = config["tasks"]
        
        # Get states from Redis
        result = {}
        for task in tasks_list:
            # Handle both dictionary and Pydantic model
            if isinstance(task, dict):
                task_id = task["id"]
                task_info = {
                    "name": task["name"],
                    "source": task["source"],
                    "field": task["field"],
                    "operator": task["operator"],
                    "value": task["value"],
                    "actions_count": len(task["actions"])
                }
            else:  # Assume Pydantic model
                task_id = task.id
                task_info = {
                    "name": task.name,
                    "source": task.source,
                    "field": task.field,
                    "operator": task.operator,
                    "value": task.value,
                    "actions_count": len(task.actions)
                }
            
            # Get current state
            triggered = get_rule_state(task_id)
            task_info["triggered"] = triggered
            
            # Add to result
            result[task_id] = task_info
            
            # Add timestamps if available
            triggered_at = redis_client.get(f"rule_triggered_at:{task_id}")
            if triggered_at:
                result[task_id]["last_triggered"] = triggered_at.decode('utf-8')
                
            cleared_at = redis_client.get(f"rule_cleared_at:{task_id}")
            if cleared_at:
                result[task_id]["last_cleared"] = cleared_at.decode('utf-8')
        
        return result
    except Exception as e:
        logger.error(f"Error getting rule status: {e}", exc_info=True)
        return {"error": str(e)}