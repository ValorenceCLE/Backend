"""
Relay control and scheduling tasks.

This module defines Celery tasks for controlling relays (on/off/pulse operations)
and managing relay schedules based on configured time patterns.
"""
import logging
from datetime import datetime
from typing import Dict, Any, List
from celery_app import app
from app.core.tasks.common import run_task_with_new_loop, TaskMetrics
from app.services.controller import RelayControl
from app.core.env_settings import env

logger = logging.getLogger(__name__)

@app.task
def check_schedules() -> Dict[str, Any]:
    """
    Check all relay schedules and update relay states as needed.
    Runs periodically via Celery Beat.
    
    Returns:
        Dict with schedule check results
    """
    with TaskMetrics("check_schedules") as metrics:
        try:
            # Get configuration
            from app.core.config import config_manager
            config = config_manager.get_config()
            
            # Track results
            results = {
                "checked": 0,
                "updated": 0,
                "errors": 0,
                "relays": {}
            }
            
            # Process each relay
            for relay in config.relays:
                # Skip disabled relays
                if not relay.enabled:
                    continue
                    
                # Skip relays without a schedule or with disabled schedule
                schedule = relay.schedule
                if not schedule or not getattr(schedule, 'enabled', False):
                    continue
                    
                relay_id = relay.id
                metrics.increment("checked")
                results["checked"] += 1
                
                try:
                    # Determine if relay should be on
                    should_be_on = _should_be_on(relay)
                    
                    # Get current state directly
                    controller = RelayControl(relay_id)
                    current_state = controller.state
                    is_on = current_state == 1
                    
                    # Store relay check result
                    results["relays"][relay_id] = {
                        "name": relay.name,
                        "current_state": "ON" if is_on else "OFF",
                        "scheduled_state": "ON" if should_be_on else "OFF",
                        "action_needed": should_be_on != is_on
                    }
                    
                    # Update state if needed
                    if should_be_on != is_on:
                        logger.info(f"Schedule: Setting relay {relay_id} ({relay.name}) to {'ON' if should_be_on else 'OFF'}")
                        
                        if should_be_on:
                            task = set_relay_state.delay(relay_id, True)
                        else:
                            task = set_relay_state.delay(relay_id, False)
                            
                        results["relays"][relay_id]["task_id"] = task.id
                        results["updated"] += 1
                        metrics.increment("updated")
                except Exception as e:
                    logger.error(f"Error checking relay {relay_id}: {e}")
                    results["errors"] += 1
                    metrics.increment("errors")
                    results["relays"][relay_id] = {
                        "error": str(e)
                    }
            
            # Add timestamp
            results["timestamp"] = datetime.now().isoformat()
            
            # Log summary
            if results["updated"] > 0:
                logger.info(f"Updated {results['updated']} relays based on schedules")
            elif results["checked"] > 0:
                logger.info(f"Checked {results['checked']} relay schedules - no updates needed")
                
            return results
            
        except Exception as e:
            logger.error(f"Error checking schedules: {e}")
            metrics.increment("errors")
            return {"error": str(e)}

def _should_be_on(relay) -> bool:
    """
    Determine if a relay should be ON based on its schedule and the current time.
    
    Args:
        relay: Relay configuration object
        
    Returns:
        True if the relay should be ON, False otherwise
    """
    # Get schedule details - handle both dict and object models
    schedule = relay.schedule
    if not schedule or not getattr(schedule, 'enabled', False):
        return False
    
    # Get schedule parameters
    on_time = getattr(schedule, 'on_time', '00:00') or '00:00'
    off_time = getattr(schedule, 'off_time', '23:59') or '23:59'
    days_mask = getattr(schedule, 'days_mask', 0)
    
    # Get current time and day of week
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    
    # Get current day name and bit value
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    current_day_name = day_names[now.weekday()]
    day_bit = env.DAY_BITMASK.get(current_day_name, 0)
    
    # Check if today is scheduled
    if not (days_mask & day_bit):
        return False
    
    # Handle schedules that span midnight
    if on_time > off_time:
        # e.g., ON at 22:00, OFF at 06:00
        return current_time >= on_time or current_time < off_time
    else:
        # Normal schedule (e.g., ON at 08:00, OFF at 17:00)
        return on_time <= current_time < off_time

@app.task
def get_relay_state(relay_id: str) -> Dict[str, Any]:
    """
    Get the current state of a single relay.
    
    Args:
        relay_id: Identifier for the relay
        
    Returns:
        Dict with relay state information
    """
    with TaskMetrics(f"get_relay_state:{relay_id}") as metrics:
        try:
            controller = RelayControl(relay_id)
            state = controller.state
            
            # Use our controller to get the relay name from config if available
            name = None
            try:
                from app.core.config import config_manager
                config = config_manager.get_config()
                for relay in config.relays:
                    if relay.id == relay_id:
                        name = relay.name
                        break
            except Exception:
                pass
                
            return {
                "status": "success",
                "relay_id": relay_id,
                "name": name,
                "state": state,
                "state_text": "ON" if state == 1 else "OFF",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.exception(f"Error getting state for relay {relay_id}: {e}")
            metrics.increment("errors")
            return {
                "status": "error",
                "message": str(e),
                "relay_id": relay_id,
                "state": None
            }

@app.task
@run_task_with_new_loop
async def set_relay_state(relay_id: str, state: bool) -> Dict[str, Any]:
    """
    Set a relay to ON or OFF.
    
    Args:
        relay_id: Identifier for the relay
        state: True for ON, False for OFF
        
    Returns:
        Dict with operation result
    """
    with TaskMetrics(f"set_relay_state:{relay_id}") as metrics:
        try:
            # Get the controller
            controller = RelayControl(relay_id)
            
            # Execute the appropriate operation
            if state:
                logger.info(f"Setting relay {relay_id} to ON")
                result = await controller.turn_on()
            else:
                logger.info(f"Setting relay {relay_id} to OFF")
                result = await controller.turn_off()
                
            # Add timestamp and verify success
            result["timestamp"] = datetime.now().isoformat()
            
            if result.get("status") != "success":
                metrics.increment("errors")
                
            return result
        except Exception as e:
            logger.exception(f"Error setting relay {relay_id} to {'ON' if state else 'OFF'}: {e}")
            metrics.increment("errors")
            return {
                "status": "error",
                "message": str(e),
                "relay_id": relay_id,
                "state": None
            }

@app.task
@run_task_with_new_loop
async def pulse_relay(relay_id: str, duration: float) -> Dict[str, Any]:
    """
    Pulse a relay by toggling it, waiting for a duration, then toggling back.
    
    Args:
        relay_id: Identifier for the relay
        duration: Pulse duration in seconds
        
    Returns:
        Dict with operation result
    """
    with TaskMetrics(f"pulse_relay:{relay_id}") as metrics:
        try:
            # Get the controller
            controller = RelayControl(relay_id)
            
            # Log the operation
            logger.info(f"Pulsing relay {relay_id} for {duration}s")
            
            # Toggle the relay immediately
            initial_result = await controller.toggle()
            initial_state = initial_result.get("state")
            
            # Schedule a separate task to toggle it back after the duration
            toggle_back_task = set_relay_state.apply_async(
                args=[relay_id, initial_state == 0],  # Toggle back to original state
                countdown=duration  # Schedule to run after duration seconds
            )
            
            # Build result with more detail
            result = {
                "status": "success",
                "relay_id": relay_id,
                "message": f"Relay pulse initiated for {duration} seconds",
                "initial_state": "ON" if initial_state == 1 else "OFF",
                "return_state": "ON" if initial_state == 0 else "OFF",
                "pulse_duration": duration,
                "toggle_back_task_id": toggle_back_task.id,
                "timestamp": datetime.now().isoformat()
            }
            
            metrics.set("duration", duration)
            return result
            
        except Exception as e:
            logger.exception(f"Error pulsing relay {relay_id}: {e}")
            metrics.increment("errors")
            return {
                "status": "error",
                "message": str(e),
                "relay_id": relay_id,
                "state": None
            }

@app.task
def get_all_relay_states(relay_ids: List[str]) -> Dict[str, Any]:
    """
    Get the states of multiple relays at once.
    
    Args:
        relay_ids: List of relay identifiers
        
    Returns:
        Dict mapping relay IDs directly to their states (0 or 1)
    """
    with TaskMetrics("get_all_relay_states") as metrics:
        try:
            # Simple result format expected by the frontend
            result = {}
            errors = 0
            
            # Process each relay
            for relay_id in relay_ids:
                try:
                    controller = RelayControl(relay_id)
                    state = controller.state
                    
                    # Store ONLY the state value in the result
                    result[relay_id] = state
                    metrics.increment("processed")
                except Exception as e:
                    logger.error(f"Error getting state for relay {relay_id}: {e}")
                    # Set state to 0 (OFF) on errors for frontend compatibility
                    result[relay_id] = 0
                    errors += 1
                    metrics.increment("errors")
            
            metrics.set("errors", errors)
            metrics.set("success", len(relay_ids) - errors)
            
            return result
        except Exception as e:
            logger.exception(f"Error getting multiple relay states: {e}")
            metrics.increment("errors")
            return {}  # Return empty dict on error