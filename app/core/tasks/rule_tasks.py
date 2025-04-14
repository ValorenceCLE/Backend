"""
Rule evaluation tasks.

This module defines Celery tasks for evaluating sensor data against 
defined rules and executing actions.
"""
import asyncio
import logging
from typing import Dict, Any, List
from celery import shared_task
from app.utils.validator import load_config, Task
from app.services.controller import RelayControl

logger = logging.getLogger(__name__)

@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3
)
def evaluate_rules(source: str, data: Dict[str, float]):
    """
    Evaluate a data point against all tasks that use this source.
    
    Args:
        source (str): The source of the data (e.g., "relay_1").
        data (Dict[str, float]): The data point (e.g., {"volts": 12.3, "amps": 0.5}).
    """
    logger.debug(f"Evaluating rules for source {source}")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_evaluate_rules_async(source, data))
        return True
    except Exception as e:
        logger.error(f"Error evaluating rules: {e}")
        return False
    finally:
        loop.close()

async def _evaluate_rules_async(source: str, data: Dict[str, float]):
    """Asynchronously evaluate rules for a data source"""
    try:
        # Load configuration to get tasks
        config = load_config("config/custom_config.json")
        
        # Build source-to-tasks mapping
        source_to_tasks = {}
        for task_id, task in config.tasks.items():
            if task.source not in source_to_tasks:
                source_to_tasks[task.source] = []
            source_to_tasks[task.source].append((task_id, task))
        
        # Skip if no tasks for this source
        if source not in source_to_tasks:
            return
        
        task_items = source_to_tasks[source]
        logger.debug(f"Evaluating {len(task_items)} tasks for source {source}")
        
        # Global state tracking
        task_states = {}
        
        for task_id, task in task_items:
            # Skip if the field doesn't exist in the data
            if task.field not in data:
                logger.debug(f"Field '{task.field}' not in data for task '{task.name}' ({task_id})")
                continue
            
            # Evaluate the condition
            value = data[task.field]
            condition_met = _evaluate_condition(value, task.operator, task.value)
            previously_triggered = task_states.get(task_id, False)
            
            logger.debug(f"Task '{task.name}' ({task_id}): {value} {task.operator} {task.value} = {condition_met}, previously_triggered={previously_triggered}")
            
            # Handle state changes
            if condition_met and not previously_triggered:
                # NOT TRIGGERED -> TRIGGERED (alert_start)
                task_states[task_id] = True
                await _handle_task_triggered(task_id, task, data)
            elif not condition_met and previously_triggered:
                # TRIGGERED -> NOT TRIGGERED (alert_clear)
                task_states[task_id] = False
                await _handle_task_cleared(task_id, task, data)
                
    except Exception as e:
        logger.error(f"Error evaluating rules for {source}: {e}")

def _evaluate_condition(value: float, operator: str, threshold: float) -> bool:
    """
    Evaluate a condition based on the operator and threshold.
    """
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

async def _handle_task_triggered(task_id: str, task: Task, data: Dict[str, float]):
    """
    Handle a task being triggered (transition from not triggered to triggered).
    """
    logger.info(f"Task '{task.name}' ({task_id}) triggered")
    
    # Execute all actions for this task
    for action in task.actions:
        await _execute_action(action, task, data)

async def _handle_task_cleared(task_id: str, task: Task, data: Dict[str, float]):
    """
    Handle a task being cleared (transition from triggered to not triggered).
    """
    logger.info(f"Task '{task.name}' ({task_id}) cleared")
    # No specific actions for clearing in this implementation

async def _execute_action(action: Any, task: Task, data: Dict[str, float]):
    """
    Execute a single action from a task.
    """
    try:
        if action.type == "io":
            await _execute_io_action(action)
        elif action.type == "log":
            await _execute_log_action(action, task, data)
        elif action.type == "reboot":
            await _execute_reboot_action()
        else:
            logger.error(f"Unknown action type: {action.type}")
    except Exception as e:
        logger.error(f"Error executing action: {e}")

async def _execute_io_action(action: Any):
    """
    Execute an IO action (relay control).
    """
    if not action.target or not action.state:
        logger.error("IO action missing target or state")
        return
    
    target = action.target
    state = action.state.lower()
    
    try:
        controller = RelayControl(target)
        
        if state == "on":
            result = await controller.turn_on()
            logger.info(f"IO action: turned relay {target} ON - Success: {result.get('status') == 'success'}")
        elif state == "off":
            result = await controller.turn_off()
            logger.info(f"IO action: turned relay {target} OFF - Success: {result.get('status') == 'success'}")
        elif state == "pulse":
            # Get pulse duration from config
            from app.utils.validator import load_config
            config = load_config("config/custom_config.json")
            relay_config = next((r for r in config.relays if r.id == target), None)
            pulse_time = relay_config.pulse_time if relay_config else 5
            
            # Execute pulse
            initial_state = controller.state
            if initial_state == 1:
                await controller.turn_off()
            else:
                await controller.turn_on()
                
            await asyncio.sleep(pulse_time)
            
            if initial_state == 1:
                await controller.turn_on()
            else:
                await controller.turn_off()
                
            logger.info(f"IO action: pulsed relay {target} for {pulse_time}s")
        else:
            logger.error(f"Unknown IO state: {state}")
    except Exception as e:
        logger.error(f"Error executing IO action on {target}: {e}")

async def _execute_log_action(action: Any, task: Task, data: Dict[str, float]):
    """
    Execute a log action.
    """
    message = action.message or f"Alert from task '{task.name}'"
    logger.info(f"Task '{task.name}' triggered log action: {message}")
    logger.info(f"Task data: {data}")

async def _execute_reboot_action():
    """
    Execute a reboot action.
    """
    logger.warning("System reboot requested by task action")
    try:
        # Schedule the reboot to happen after a short delay
        import subprocess
        subprocess.Popen(["sudo", "reboot"])
    except Exception as e:
        logger.error(f"Error scheduling reboot: {e}")