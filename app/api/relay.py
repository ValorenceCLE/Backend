import logging
import asyncio
from fastapi import APIRouter, HTTPException, status, Depends, Query, WebSocket
from app.utils.dependencies import internal_or_user_auth, verify_token_ws
from celery_app import app as celery_app
from app.core.config import config_manager  # Updated import path
from app.utils.websocket_utils import (
    ws_manager,
    websocket_connection,
    safe_send_json,
    safe_send_text,
    safe_close
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(
    prefix="/io",
    tags=["Relay API"],
    dependencies=[Depends(internal_or_user_auth)]
)
websocket_router = APIRouter(
    prefix="/io", 
    tags=["Relay WebSocket API"]
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

async def relay_states_polling_loop(websocket: WebSocket, enabled_only: bool, interval_seconds: float = 1.0):
    """
    Simple polling loop for relay states that sends updates at regular intervals.
    
    Args:
        websocket: WebSocket connection
        enabled_only: If True, only include enabled relays
        interval_seconds: Polling interval in seconds
    """
    try:
        while True:
            try:
                # Get fresh config in every loop in case relays were enabled/disabled
                config = config_manager.get_config()
                
                if enabled_only:
                    # Only get enabled relays
                    relay_ids = [relay.id for relay in config.relays if relay.enabled]
                else:
                    # Get all relays
                    relay_ids = [relay.id for relay in config.relays]
                
                # Skip if no relays to check
                if not relay_ids:
                    await asyncio.sleep(interval_seconds)
                    continue
                
                # Get relay states with Celery task
                task = celery_app.send_task(
                    'app.core.tasks.relay_tasks.get_all_relay_states',
                    args=[relay_ids],
                )
                states = task.get(timeout=min(interval_seconds * 0.8, 2.0))
                
                # Send states to the client
                if states:
                    if not await safe_send_json(websocket, states):
                        # Connection closed
                        break
                
            except Exception as e:
                logger.error(f"Error in relay states polling loop: {e}")
                # Continue the loop even if there was an error, but log it
            
            # Wait for next interval
            await asyncio.sleep(interval_seconds)
            
    except Exception as e:
        logger.exception(f"Unhandled error in relay states WebSocket: {e}")

# WebSocket endpoint for all relay states - using the websocket_router
@websocket_router.websocket("/relays/state/ws")
async def all_relay_states_websocket(
    websocket: WebSocket,
    token: str = Query(None),
    interval: float = Query(2.0, ge=0.5, le=10.0)
):
    """WebSocket endpoint to stream all relay states"""
    connection_id = f"all_relay_states_{id(websocket)}"
    
    # Handle authentication manually
    await websocket.accept()
    
    # Authenticate if token provided
    if token:
        try:
            await verify_token_ws(token)
        except HTTPException as e:
            await websocket.send_text(f"Authentication failed: {e.detail}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    
    # Register connection
    ws_manager.register_connection(connection_id, websocket)
    
    try:
        logger.info(f"Started all relay states WebSocket with {interval}s interval")
        await relay_states_polling_loop(websocket, enabled_only=False, interval_seconds=interval)
    finally:
        ws_manager.unregister_connection(connection_id, websocket)

# WebSocket endpoint for enabled relay states - using the websocket_router
@websocket_router.websocket("/relays/enabled/state/ws")
async def enabled_relay_states_websocket(
    websocket: WebSocket,
    token: str = Query(None),
    interval: float = Query(2.0, ge=0.5, le=10.0)
):
    """WebSocket endpoint to stream enabled relay states"""
    connection_id = f"enabled_relay_states_{id(websocket)}"
    
    # Handle authentication manually
    await websocket.accept()
    
    # Authenticate if token provided
    if token:
        try:
            await verify_token_ws(token)
        except HTTPException as e:
            await websocket.send_text(f"Authentication failed: {e.detail}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    
    # Register connection
    ws_manager.register_connection(connection_id, websocket)
    
    try:
        logger.info(f"Started enabled relay states WebSocket with {interval}s interval")
        await relay_states_polling_loop(websocket, enabled_only=True, interval_seconds=interval)
    finally:
        ws_manager.unregister_connection(connection_id, websocket)