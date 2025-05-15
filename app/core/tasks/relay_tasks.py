"""
app/core/tasks/relay_tasks.py
Relay control and scheduling tasks.

This module defines Celery tasks for controlling relays and managing
their schedules.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List
from celery_app import app
from app.services.controller import RelayControl
from app.core.services.config_manager import config_manager

logger = logging.getLogger(__name__)

@app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3
)
def check_schedules(self):
    """
    Check all relay schedules and update relay states as needed.
    
    This task is scheduled to run periodically by Celery Beat.
    """
    logger.info("Checking relay schedules")
    
    try:
        # Get configuration using the manager
        config = config_manager.get_full_config()
        
        # Check if relays key exists
        if "relays" not in config:
            logger.warning("No 'relays' key in configuration, falling back to direct loading")
            # Fall back to direct loading from file
            try:
                from app.utils.validator import load_config
                pydantic_config = load_config("app/config/custom_config.json")
                relays_list = pydantic_config.relays
            except Exception as e:
                logger.error(f"Failed to load relays from file: {e}")
                return False
        else:
            relays_list = config["relays"]
        
        # Process each relay synchronously
        for relay in relays_list:
            # Handle both dictionary and Pydantic model
            if isinstance(relay, dict):
                relay_id = relay.get("id")
                enabled = relay.get("enabled", False)
                schedule = relay.get("schedule", {})
                # Check if schedule is boolean False
                if schedule is False:
                    continue
                schedule_enabled = schedule.get("enabled", False) if isinstance(schedule, dict) else False
            else:  # Assume Pydantic model
                relay_id = relay.id
                enabled = relay.enabled
                schedule = relay.schedule
                # Check if schedule is boolean False
                if schedule is False:
                    continue
                schedule_enabled = schedule.enabled if hasattr(schedule, "enabled") else False
            
            # Skip disabled relays
            if not enabled:
                continue
                
            # Skip relays without a schedule or with disabled schedule
            if not schedule_enabled:
                continue
                
            # Check if the relay should be ON or OFF based on schedule
            should_be_on = _should_be_on(relay)
            
            # Get current state directly
            try:
                controller = RelayControl(relay_id)
                current_state = controller.state
                is_on = current_state == 1
                
                # Update state if needed
                if should_be_on != is_on:
                    logger.info(f"Schedule: Setting relay {relay_id} to {'ON' if should_be_on else 'OFF'}")
                    if should_be_on:
                        set_relay_state.delay(relay_id, True)
                    else:
                        set_relay_state.delay(relay_id, False)
            except Exception as e:
                logger.error(f"Error checking relay {relay_id}: {e}")
        
        return True
    except Exception as e:
        logger.error(f"Error checking schedules: {e}")
        return False

def _should_be_on(relay) -> bool:
    """
    Determine if a relay should be ON based on its schedule and the current time.
    """
    # Get schedule details - handle both dict and Pydantic model
    if isinstance(relay, dict):
        schedule = relay.get("schedule", {})
        if schedule is False:
            return False
        
        schedule_enabled = schedule.get("enabled", False) if isinstance(schedule, dict) else False
        on_time = schedule.get("on_time") if isinstance(schedule, dict) else getattr(schedule, "on_time", None) 
        off_time = schedule.get("off_time") if isinstance(schedule, dict) else getattr(schedule, "off_time", None)
        days_mask = schedule.get("days_mask", 0) if isinstance(schedule, dict) else getattr(schedule, "days_mask", 0)
    else:  # Pydantic model
        schedule = relay.schedule
        if schedule is False:
            return False
        
        schedule_enabled = getattr(schedule, "enabled", False)
        on_time = getattr(schedule, "on_time", None)
        off_time = getattr(schedule, "off_time", None)
        days_mask = getattr(schedule, "days_mask", 0)
    
    if not schedule_enabled:
        return False
        
    # Get current time and day of week
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    
    # Get current day name
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    current_day_name = day_names[now.weekday()]
    
    # Get day bit value from env settings
    from app.core.env_settings import env
    day_bit = env.DAY_BITMASK.get(current_day_name, 0)
    
    # Check if today is scheduled
    if not (days_mask & day_bit):
        return False
        
    # Use defaults if not specified
    on_time = on_time or "00:00"
    off_time = off_time or "23:59"
    
    # Handle schedules that span midnight
    if on_time > off_time:
        # e.g., ON at 22:00, OFF at 06:00
        return current_time >= on_time or current_time < off_time
    else:
        # Normal schedule (e.g., ON at 08:00, OFF at 17:00)
        return on_time <= current_time < off_time

@app.task(bind=True, max_retries=2)
def get_relay_state(self, relay_id: str) -> Dict[str, Any]:
    """
    Get the current state of a relay.
    """
    try:
        controller = RelayControl(relay_id)
        state = controller.state
        return {
            "status": "success",
            "relay_id": relay_id,
            "state": state
        }
    except Exception as e:
        logger.exception(f"Error getting state for relay {relay_id}: {e}")
        self.retry(exc=e)
        return {
            "status": "error",
            "message": str(e),
            "relay_id": relay_id,
            "state": None
        }

@app.task(bind=True, max_retries=3)
def set_relay_state(self, relay_id: str, state: bool) -> Dict[str, Any]:
    """
    Set a relay to ON or OFF.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        controller = RelayControl(relay_id)
        
        # Run the async controller operation in the event loop
        if state:
            result = loop.run_until_complete(controller.turn_on())
        else:
            result = loop.run_until_complete(controller.turn_off())
            
        return result
    except Exception as e:
        logger.exception(f"Error setting relay {relay_id} to {'ON' if state else 'OFF'}: {e}")
        self.retry(exc=e)
        return {
            "status": "error",
            "message": str(e),
            "relay_id": relay_id,
            "state": None
        }
    finally:
        loop.close()

@app.task(bind=True, max_retries=3)
def pulse_relay(self, relay_id: str, duration: float) -> Dict[str, Any]:
    """
    Pulse a relay by toggling it, waiting for a duration, then toggling back.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        controller = RelayControl(relay_id)
        
        # Toggle the relay immediately
        initial_result = loop.run_until_complete(controller.toggle())
        initial_state = initial_result.get("state")
        
        # Schedule a separate task to toggle it back after the duration
        # This will run in a separate process/thread via Celery
        toggle_back_task = set_relay_state.apply_async(
            args=[relay_id, initial_state == 0],  # Toggle back to original state
            countdown=duration  # Schedule to run after duration seconds
        )
        
        return {
            "status": "success",
            "relay_id": relay_id,
            "message": f"Relay pulse initiated for {duration} seconds",
            "state": initial_state,
            "toggle_back_task_id": toggle_back_task.id
        }
    except Exception as e:
        logger.exception(f"Error pulsing relay {relay_id}: {e}")
        self.retry(exc=e)
        return {
            "status": "error",
            "message": str(e),
            "relay_id": relay_id,
            "state": None
        }
    finally:
        loop.close()


@app.task(bind=True, max_retries=2)
def get_all_relay_states(self, relay_ids: List[str]) -> Dict[str, int]:
    """
    Get the states of multiple relays at once.
    """
    try:
        result = {}
        for relay_id in relay_ids:
            try:
                controller = RelayControl(relay_id)
                result[relay_id] = controller.state
            except Exception as e:
                logger.error(f"Error getting state for relay {relay_id}: {e}")
                result[relay_id] = None
        
        return result
    except Exception as e:
        logger.exception(f"Error getting multiple relay states: {e}")
        self.retry(exc=e)
        return {}