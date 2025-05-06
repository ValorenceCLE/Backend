"""
app/core/tasks.py
Enhanced Task Manager for handling automated tasks and rules.

This module processes data from sensors and executes actions based on configured rules.
Includes improved error handling, state management, and concurrent task execution.
"""
import asyncio
import subprocess
import time
from typing import Dict, List, Any
import logging
from app.utils.validator import Task, TaskAction
from app.services.controller import RelayControl
import redis
import json

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set to DEBUG for more verbose logging

class TaskManager:
    """
    Enhanced Task Manager with improved error handling, state management,
    and concurrent task execution.
    """
    def __init__(self, tasks: List[Task], relay_manager: RelayControl):
        """
        Initialize the TaskManager.
        
        Args:
            tasks (List[Task]): List of task configurations.
            relay_manager (RelayControl): The relay manager for controlling relays.
        """
        self.tasks = tasks
        self.relay_manager = relay_manager
        
        # Initialize Redis connection for state management
        self.redis_client = redis.Redis.from_url('redis://redis:6379/0', decode_responses=True)
        
        # Create task lookup maps
        self.task_by_id: Dict[str, Task] = {task.id: task for task in tasks}
        
        # Track task states (triggered or not)
        self.task_states: Dict[str, bool] = {}
        self._load_task_states()
        
        # Create a mapping from sources to tasks for quicker lookup
        self.source_to_tasks: Dict[str, List[Task]] = {}
        for task in tasks:
            source = task.source
            if source not in self.source_to_tasks:
                self.source_to_tasks[source] = []
            self.source_to_tasks[source].append(task)
        
        # Concurrency control
        self._running = False
        self._lock = asyncio.Lock()
        self._action_semaphore = asyncio.Semaphore(5)  # Limit concurrent actions
    
    def _load_task_states(self):
        """Load task states from Redis on startup."""
        try:
            for task in self.tasks:
                state_key = f"task_state:{task.id}"
                state = self.redis_client.get(state_key)
                self.task_states[task.id] = bool(int(state)) if state else False
                logger.debug(f"Loaded state for task {task.id}: {self.task_states[task.id]}")
        except Exception as e:
            logger.error(f"Error loading task states from Redis: {e}")
            # Initialize all states to False if Redis fails
            self.task_states = {task.id: False for task in self.tasks}
    
    def _save_task_state(self, task_id: str, state: bool):
        """Save task state to Redis."""
        try:
            state_key = f"task_state:{task_id}"
            self.redis_client.set(state_key, "1" if state else "0")
            
            # Also store timestamp of state change
            timestamp_key = f"task_state_time:{task_id}"
            self.redis_client.set(timestamp_key, time.time())
        except Exception as e:
            logger.error(f"Error saving task state to Redis: {e}")
    
    async def evaluate_data(self, source: str, data: Dict[str, float]):
        """
        Evaluate a data point against all tasks that use this source.
        
        Args:
            source (str): The source of the data (e.g., "relay_1").
            data (Dict[str, float]): The data point (e.g., {"volts": 12.3, "amps": 0.5}).
        """
        async with self._lock:  # Prevent concurrent evaluation of the same source
            try:
                # Skip if no tasks for this source
                if source not in self.source_to_tasks:
                    return
                
                tasks = self.source_to_tasks[source]
                logger.debug(f"Evaluating {len(tasks)} tasks for source {source}")
                
                # Process tasks concurrently but with limits
                evaluation_tasks = []
                for task in tasks:
                    evaluation_tasks.append(self._evaluate_single_task(task, data))
                
                await asyncio.gather(*evaluation_tasks, return_exceptions=True)
                
            except Exception as e:
                logger.error(f"Error in evaluate_data for source {source}: {e}", exc_info=True)
    
    async def _evaluate_single_task(self, task: Task, data: Dict[str, float]):
        """Evaluate a single task against data."""
        try:
            # Skip if the field doesn't exist in the data
            if task.field not in data:
                logger.debug(f"Field '{task.field}' not in data for task '{task.name}' ({task.id})")
                return
            
            # Evaluate the condition
            condition_met = self._evaluate_condition(data[task.field], task.operator, task.value)
            previously_triggered = self.task_states.get(task.id, False)
            
            logger.debug(f"Task '{task.name}' ({task.id}): condition_met={condition_met}, previously_triggered={previously_triggered}")
            
            # Handle state changes
            if condition_met and not previously_triggered:
                # NOT TRIGGERED -> TRIGGERED (alert_start)
                self.task_states[task.id] = True
                self._save_task_state(task.id, True)
                await self._handle_task_triggered(task, data)
            elif not condition_met and previously_triggered:
                # TRIGGERED -> NOT TRIGGERED (alert_clear)
                self.task_states[task.id] = False
                self._save_task_state(task.id, False)
                await self._handle_task_cleared(task, data)
                
        except Exception as e:
            logger.error(f"Error evaluating task {task.id}: {e}", exc_info=True)
    
    def _evaluate_condition(self, value: float, operator: str, threshold: float) -> bool:
        """
        Evaluate a condition based on the operator and threshold.
        """
        try:
            logger.debug(f"Evaluating condition: {value} {operator} {threshold}")
            
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
            logger.error(f"Error in condition evaluation: {e}")
            return False
    
    async def _handle_task_triggered(self, task: Task, data: Dict[str, float]):
        """
        Handle a task being triggered (transition from not triggered to triggered).
        """
        logger.info(f"Task '{task.name}' ({task.id}) triggered")
        
        # Execute all actions for this task concurrently with semaphore
        action_tasks = []
        for action in task.actions:
            action_tasks.append(self._execute_action_with_semaphore(action, task, data))
        
        await asyncio.gather(*action_tasks, return_exceptions=True)
    
    async def _handle_task_cleared(self, task: Task, data: Dict[str, float]):
        """
        Handle a task being cleared (transition from triggered to not triggered).
        """
        logger.info(f"Task '{task.name}' ({task.id}) cleared")
        # For now, no specific actions for clearing
        # Could add notification or cleanup actions here if needed
    
    async def _execute_action_with_semaphore(self, action: TaskAction, task: Task, data: Dict[str, float]):
        """Execute an action with semaphore control."""
        async with self._action_semaphore:
            await self._execute_action(action, task, data)
    
    async def _execute_action(self, action: TaskAction, task: Task, data: Dict[str, float]):
        """
        Execute a single action from a task with enhanced error handling.
        """
        try:
            if action.type == "io":
                await self._execute_io_action(action)
            elif action.type == "log":
                await self._execute_log_action(action, task, data)
            elif action.type == "reboot":
                await self._execute_reboot_action()
            else:
                logger.error(f"Unknown action type: {action.type}")
        except Exception as e:
            logger.error(f"Error executing action {action.type} for task {task.id}: {e}", exc_info=True)
            
            # Store error in Redis for monitoring
            try:
                error_key = f"task_error:{task.id}:{action.type}"
                error_data = {
                    "error": str(e),
                    "timestamp": time.time(),
                    "task_name": task.name,
                    "action_type": action.type
                }
                self.redis_client.set(error_key, json.dumps(error_data))
                self.redis_client.expire(error_key, 86400)  # Expire after 24 hours
            except Exception as redis_error:
                logger.error(f"Failed to store error in Redis: {redis_error}")
    
    async def _execute_io_action(self, action: TaskAction):
        """
        Execute an IO action (relay control) with retry logic.
        """
        if not action.target or not action.state:
            logger.error("IO action missing target or state")
            return
        
        target = action.target
        state = action.state.lower()
        
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                if state == "on":
                    result = await self.relay_manager.set_relay_on(target)
                    logger.info(f"IO action: turned relay {target} ON - Success: {result}")
                elif state == "off":
                    result = await self.relay_manager.set_relay_off(target)
                    logger.info(f"IO action: turned relay {target} OFF - Success: {result}")
                elif state == "pulse":
                    relay_config = self.relay_manager.get_relay_by_id(target)
                    pulse_time = relay_config.pulse_time if relay_config else 5
                    result = await self.relay_manager.pulse_relay(target, pulse_time)
                    logger.info(f"IO action: pulsed relay {target} for {pulse_time}s - Success: {result}")
                else:
                    logger.error(f"Unknown IO state: {state}")
                    return
                
                if result:
                    return  # Success
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{max_retries} failed for IO action on {target}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"All retry attempts failed for IO action on {target}")
    
    async def _execute_log_action(self, action: TaskAction, task: Task, data: Dict[str, float]):
        """
        Execute a log action with enhanced logging.
        """
        message = action.message or f"Alert from task '{task.name}'"
        logger.info(f"Task '{task.name}' triggered log action: {message}")
        logger.info(f"Task data: {data}")
        
        # Store log action in Redis for monitoring
        try:
            log_key = f"task_log:{task.id}:{int(time.time())}"
            log_data = {
                "task_name": task.name,
                "message": message,
                "data": data,
                "timestamp": time.time()
            }
            self.redis_client.set(log_key, json.dumps(log_data))
            self.redis_client.expire(log_key, 604800)  # Expire after 7 days
        except Exception as e:
            logger.error(f"Failed to store log action in Redis: {e}")
    
    async def _execute_reboot_action(self):
        """
        Execute a reboot action with safety checks.
        """
        logger.warning("System reboot requested by task action")
        try:
            # Check if we're already scheduled for reboot
            reboot_key = "system_reboot_scheduled"
            if self.redis_client.exists(reboot_key):
                logger.info("System reboot already scheduled, skipping")
                return
            
            # Schedule the reboot
            self.redis_client.set(reboot_key, "1")
            self.redis_client.expire(reboot_key, 60)  # Expire after 1 minute
            
            # Schedule the reboot to happen after a short delay
            asyncio.create_task(self._delayed_reboot())
        except Exception as e:
            logger.error(f"Error scheduling reboot: {e}")
    
    async def _delayed_reboot(self, delay: int = 5):
        """
        Reboot the system after a delay.
        """
        logger.warning(f"System will reboot in {delay} seconds")
        await asyncio.sleep(delay)
        try:
            subprocess.run(["sudo", "reboot"])
        except Exception as e:
            logger.error(f"Failed to reboot system: {e}")
    
    async def run(self):
        """
        Start the task manager.
        """
        if self._running:
            logger.warning("Task manager already running")
            return
        
        self._running = True
        logger.info(f"Task manager started with {len(self.tasks)} tasks")
        
        # This implementation doesn't have a main loop since tasks are evaluated on-demand
        # when data is received. We just need to keep the run() method alive.
        try:
            while self._running:
                await asyncio.sleep(60)  # Sleep for a minute
                
                # Optional: Perform periodic housekeeping
                await self._perform_housekeeping()
                
        except asyncio.CancelledError:
            logger.info("Task manager cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in task manager: {e}")
        finally:
            self._running = False
    
    async def _perform_housekeeping(self):
        """Perform periodic housekeeping tasks."""
        try:
            # Check Redis connection
            if not self.redis_client.ping():
                logger.warning("Redis connection lost, attempting to reconnect")
                self.redis_client = redis.Redis.from_url('redis://redis:6379/0', decode_responses=True)
                
            # Log task manager status
            logger.debug(f"Task manager status: {len(self.task_states)} tasks tracked")
        except Exception as e:
            logger.error(f"Error in housekeeping: {e}")
    
    async def shutdown(self):
        """
        Shut down the task manager gracefully.
        """
        if not self._running:
            return
        
        self._running = False
        logger.info("Shutting down task manager")
        
        # Save all task states
        for task_id, state in self.task_states.items():
            self._save_task_state(task_id, state)