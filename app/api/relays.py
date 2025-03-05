from fastapi import Request, APIRouter, HTTPException, Depends, status
import logging
from typing import Dict, Any

try:
    from app.utils.dependencies import require_role
    from app.services.relay_controller import Controller  # our fully async controller
except ImportError:
    from utils.dependencies import require_role
    from services.relay_controller import Controller

router = APIRouter(prefix="/relay", tags=["Relay Configuration API"])
logger = logging.getLogger(__name__)

def get_controller(relay_id: str, request: Request) -> Controller:
    """
    Retrieve the pre-initialized Controller for a given relay_id.
    This assumes that app.state.relay_controllers is a dict mapping relay_id to Controller.
    """
    controller = request.app.state.relay_controllers.get(relay_id)
    if controller is None:
        logger.error(f"Relay controller for '{relay_id}' not found.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relay '{relay_id}' not found"
        )
    return controller

# Use dependency that allows both "user" and "admin" roles.
allowed_roles = ["user", "admin"]

@router.get(
    "/{relay_id}",
    summary="Retrieve relay configuration",
    dependencies=[Depends(require_role(allowed_roles))]
)
async def get_relay_config(relay_id: str, request: Request) -> Dict[str, Any]:
    config = request.app.state.config.get("relays", {}).get(relay_id)
    if config is None:
        logger.error(f"Relay configuration for '{relay_id}' not found.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relay configuration for '{relay_id}' not found"
        )
    return config

@router.get(
    "/{relay_id}/state",
    summary="Retrieve relay state",
    dependencies=[Depends(require_role(allowed_roles))]
)
async def get_relay_state(relay_id: str, request: Request) -> Dict[str, str]:
    controller = get_controller(relay_id, request)
    try:
        state = await controller.async_check_state()
    except Exception as e:
        logger.exception(f"Error checking state for relay '{relay_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving relay state"
        )
    return {"relay_id": relay_id, "state": "on" if state else "off"}

@router.post(
    "/{relay_id}/state",
    summary="Update relay state",
    dependencies=[Depends(require_role(allowed_roles))]
)
async def update_relay_state(relay_id: str, state: str, request: Request) -> Dict[str, str]:
    if state not in ("on", "off"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state. Must be 'on' or 'off'."
        )
    controller = get_controller(relay_id, request)
    try:
        if state == "on":
            await controller.async_turn_on()
        else:
            await controller.async_turn_off()
    except Exception as e:
        logger.exception(f"Error updating state for relay '{relay_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating relay state"
        )
    return {"message": f"Relay '{relay_id}' state updated to '{state}'"}

@router.post(
    "/{relay_id}/pulse",
    summary="Pulse relay",
    dependencies=[Depends(require_role(allowed_roles))]
)
async def pulse_relay(relay_id: str, request: Request) -> Dict[str, str]:
    """
    Pulse the relay using the pulseTime defined in the configuration.
    """
    controller = get_controller(relay_id, request)
    try:
        await controller.async_pulse()
    except Exception as e:
        logger.exception(f"Error pulsing relay '{relay_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error pulsing relay"
        )
    return {"message": f"Relay '{relay_id}' pulsed for {controller.pulseTime} seconds"}
