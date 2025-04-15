"""
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
from app.utils.validator import load_config, RelayConfig

logger = logging.getLogger(__name__)

@app.task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3
)
def check_schedules():
    """
    Check all relay schedules and update relay states as needed.
    
    This task is scheduled to run periodically by Celery Beat.
    """
    logger.debug("Checking relay schedules")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_check_all_schedules())
        return True
    except Exception as e:
        logger.error(f"Error checking schedules: {e}")
        return False
    finally:
        loop.close()

async def _check_all_schedules():
    """Check all relay schedules and update states"""
    try:
        # Load current configuration
        config = load_config("app/config/custom_config.json")
        
        # Process each relay
        for relay in config.relays:
            # Skip disabled relays
            if not relay.enabled:
                continue
                
            # Skip relays without a schedule
            if not relay.schedule or not getattr(relay.schedule, "enabled", False):
                continue
                
            # Check if the relay should be ON or OFF based on schedule
            should_be_on = _should_be_on(relay)
            
            # Get current state
            try:
                controller = RelayControl(relay.id)
                current_state = controller.state
                is_on = current_state == 1
                
                # Update state if needed
                if should_be_on != is_on:
                    logger.info(f"Schedule: Changing relay {relay.id} to {'ON' if should_be_on else 'OFF'}")
                    if should_be_on:
                        await controller.turn_on()
                    else:
                        await controller.turn_off()
            except Exception as e:
                logger.error(f"Error updating relay {relay.id}: {e}")
                
    except Exception as e:
        logger.error(f"Error processing schedules: {e}")

def _should_be_on(relay: RelayConfig) -> bool:
    """
    Determine if a relay should be ON based on its schedule and the current time.
    """
    # Get schedule details
    schedule = relay.schedule
    if not hasattr(schedule, "enabled") or not schedule.enabled:
        return False
        
    # Get current time and day of week
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    
    # Convert day of week to bitmask
    # Monday=0 (bit 4), Tuesday=1 (bit 8), etc.
    day_of_week = now.weekday()
    day_bit = 4 << day_of_week  # Start at bit 2 (value 4)
    
    # Check if today is scheduled
    if not (schedule.days_mask & day_bit):
        return False
        
    # Get schedule times
    on_time = schedule.on_time or "00:00"
    off_time = schedule.off_time or "23:59"
    
    # Handle schedules that span midnight
    if on_time > off_time:
        # e.g., ON at 22:00, OFF at 06:00
        return current_time >= on_time or current_time < off_time
    else:
        # Normal schedule (e.g., ON at 08:00, OFF at 17:00)
        return on_time <= current_time < off_time



logger = logging.getLogger(__name__)

@app.task
def get_relay_state(relay_id: str) -> Dict[str, Any]:
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
        return {
            "status": "error",
            "message": str(e),
            "relay_id": relay_id,
            "state": None
        }

@app.task
def set_relay_state(relay_id: str, state: bool) -> Dict[str, Any]:
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
        return {
            "status": "error",
            "message": str(e),
            "relay_id": relay_id,
            "state": None
        }
    finally:
        loop.close()

@app.task
def pulse_relay(relay_id: str, duration: float = 5.0) -> Dict[str, Any]:
    """
    Pulse a relay by toggling it, waiting for a duration, then toggling back.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        controller = RelayControl(relay_id)
        
        # Toggle the relay
        loop.run_until_complete(controller.toggle())
        
        # Wait for specified duration
        loop.run_until_complete(asyncio.sleep(duration))
        
        # Toggle back
        result = loop.run_until_complete(controller.toggle())
        
        return {
            "status": "success",
            "relay_id": relay_id,
            "message": f"Relay pulsed for {duration} seconds",
            "state": result.get("state")
        }
    except Exception as e:
        logger.exception(f"Error pulsing relay {relay_id}: {e}")
        return {
            "status": "error",
            "message": str(e),
            "relay_id": relay_id,
            "state": None
        }
    finally:
        loop.close()

@app.task
def get_all_relay_states(relay_ids: List[str]) -> Dict[str, int]:
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
        return {}