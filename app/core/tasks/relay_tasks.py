"""
Relay control and scheduling tasks.

This module defines Celery tasks for controlling relays and managing
their schedules.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List
from celery import shared_task
from app.services.controller import RelayControl
from app.utils.validator import load_config, RelayConfig

logger = logging.getLogger(__name__)

@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
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
        config = load_config("config/custom_config.json")
        
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

@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3
)
def set_relay_state(relay_id: str, state: bool):
    """
    Set a relay to ON or OFF.
    
    This task can be called from API endpoints or other tasks.
    """
    logger.info(f"Setting relay {relay_id} to {'ON' if state else 'OFF'}")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_set_relay_state(relay_id, state))
        return result
    except Exception as e:
        logger.error(f"Error setting relay state: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        loop.close()

async def _set_relay_state(relay_id: str, state: bool) -> Dict[str, Any]:
    """Asynchronously set relay state"""
    try:
        controller = RelayControl(relay_id)
        if state:
            result = await controller.turn_on()
        else:
            result = await controller.turn_off()
        return result
    except Exception as e:
        logger.error(f"Error setting relay {relay_id} to {'ON' if state else 'OFF'}: {e}")
        return {"status": "error", "message": str(e)}

@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3
)
def pulse_relay(relay_id: str, duration: float = 5.0):
    """
    Pulse a relay (toggle its state) for the specified duration.
    
    This task can be called from API endpoints or other tasks.
    """
    logger.info(f"Pulsing relay {relay_id} for {duration} seconds")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_pulse_relay(relay_id, duration))
        return result
    except Exception as e:
        logger.error(f"Error pulsing relay: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        loop.close()

async def _pulse_relay(relay_id: str, duration: float) -> Dict[str, Any]:
    """Asynchronously pulse relay"""
    try:
        controller = RelayControl(relay_id)
        
        # Get initial state
        initial_state = controller.state
        
        # Toggle state
        if initial_state == 1:
            await controller.turn_off()
        else:
            await controller.turn_on()
            
        # Wait for duration
        await asyncio.sleep(duration)
        
        # Restore initial state
        if initial_state == 1:
            await controller.turn_on()
        else:
            await controller.turn_off()
            
        return {
            "status": "success", 
            "message": f"Relay {relay_id} pulsed for {duration} seconds"
        }
    except Exception as e:
        logger.error(f"Error pulsing relay {relay_id}: {e}")
        return {"status": "error", "message": str(e)}