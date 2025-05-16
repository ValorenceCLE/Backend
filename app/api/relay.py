import logging
from fastapi import APIRouter, HTTPException, status, Depends
from app.utils.dependencies import internal_or_user_auth
from celery_app import app as celery_app
from app.core.config import config_manager  # Updated import path

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(
    prefix="/io",
    tags=["Relay API"],
    dependencies=[Depends(internal_or_user_auth)]
)

# Use the combined dependency for authentication.
@router.post("/{relay_id}/state/on")
async def turn_relay_on(relay_id: str) -> dict:
    """Submit a Celery task to turn relay on"""
    try:
        # Call Celery task to handle hardware operation
        task = celery_app.send_task(
            'app.core.tasks.relay_tasks.set_relay_state',
            args=[relay_id, True],  # True means ON
        )
        
        # Wait for result with timeout
        result = task.get(timeout=10)
        
        if result.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to turn relay on"),
            )
        return {"status": "success", "state": result.get("state")}
    except Exception as e:
        logger.exception(f"Error turning relay {relay_id} on: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/{relay_id}/state/off")
async def turn_relay_off(relay_id: str) -> dict:
    """Submit a Celery task to turn relay off"""
    try:
        # Call Celery task to handle hardware operation
        task = celery_app.send_task(
            'app.core.tasks.relay_tasks.set_relay_state',
            args=[relay_id, False],  # False means OFF
        )
        
        # Wait for result with timeout
        result = task.get(timeout=10)
        
        if result.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to turn relay off"),
            )
        return {"status": "success", "state": result.get("state")}
    except Exception as e:
        logger.exception(f"Error turning relay {relay_id} off: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/{relay_id}/state/pulse")
async def pulse_relay(relay_id: str) -> dict:  # Removed Request parameter
    """Submit a Celery task to pulse a relay"""
    try:
        # Get relay config from new config system instead of request.app.state
        config = config_manager.get_config()
        relay_config = next(
            (relay for relay in config.relays if relay.id == relay_id),
            None
        )
        
        if not relay_config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Relay with ID '{relay_id}' not found in configuration."
            )
        
        pulse_time = relay_config.pulse_time
        
        # Get initial state first
        state_task = celery_app.send_task(
            'app.core.tasks.relay_tasks.get_relay_state',
            args=[relay_id],
        )
        state_result = state_task.get(timeout=None)
        initial_state = state_result.get("state", 0)
        
        # Submit pulse task
        pulse_task = celery_app.send_task(
            'app.core.tasks.relay_tasks.pulse_relay',
            args=[relay_id, pulse_time],
        )
        
        # No need to wait for completion - the pulse happens asynchronously
        return {
            "status": "success",
            "duration": pulse_time,
            "state": initial_state,
            "task_id": pulse_task.id
        }
    except Exception as e:
        logger.exception(f"Error pulsing relay {relay_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/relays/state")
async def get_all_relay_states() -> dict:  # Removed Request parameter
    """Get states of all relays via Celery task"""
    try:
        # Get all relay IDs from new config system
        config = config_manager.get_config()
        relay_ids = [relay.id for relay in config.relays]
        
        # Submit task to get all states at once
        task = celery_app.send_task(
            'app.core.tasks.relay_tasks.get_all_relay_states',
            args=[relay_ids],
        )
        
        # Wait for result with timeout
        result = task.get(timeout=5)
        return result
    except Exception as e:
        logger.exception(f"Error getting all relay states: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/relays/enabled/state")
async def enabled_relay_states() -> dict:  # Removed Request parameter
    """Get states of enabled relays via Celery task"""
    try:
        # Get enabled relay IDs from new config system
        config = config_manager.get_config()
        enabled_relays = [relay for relay in config.relays if relay.enabled]
        relay_ids = [relay.id for relay in enabled_relays]
        
        # Submit task to get enabled states at once
        task = celery_app.send_task(
            'app.core.tasks.relay_tasks.get_all_relay_states',
            args=[relay_ids],
        )
        
        # Wait for result with timeout
        result = task.get(timeout=5)
        return result
    except Exception as e:
        logger.exception(f"Error getting enabled relay states: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    
@router.get("/rules/status")
async def get_rules_status() -> dict:
    """Get status of all rules via Celery task"""
    try:
        # Submit task to get rule status
        task = celery_app.send_task(
            'app.core.tasks.rule_tasks.get_rule_status',
        )
        
        # Wait for result with timeout
        result = task.get(timeout=10)
        return result
    except Exception as e:
        logger.exception(f"Error getting rule status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )