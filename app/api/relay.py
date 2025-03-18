import asyncio
import logging
from fastapi import APIRouter, HTTPException, status, Request, Depends
from app.services.controller import RelayControl
from app.utils.dependencies import require_role, is_authenticated

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(
    prefix="/io",
    tags=["Relay API"]
)

def get_controller(relay_id: str) -> RelayControl:
    """
    Instantiate a RelayControl for the given relay_id.
    """
    try:
        return RelayControl(relay_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )

async def _pulse(controller: RelayControl, pulse_time) -> None:
    """
    Toggle the relay state to start the pulse, wait for the stored pulse_time,
    then toggle again to restore the original state.
    """
    try:
        await controller.toggle()
        await asyncio.sleep(pulse_time)
        await controller.toggle()
    except Exception as e:
        # Log the error as needed.
        logger.exception(
            f"Error during pulse operation for relay '{controller.id}': {e}"
        )

@router.post("/{relay_id}/state/on")
async def turn_relay_on(relay_id: str) -> dict:
    """
    Turn the specified relay ON.
    """
    controller = get_controller(relay_id)
    result = await controller.turn_on()
    if result.get("status") != "success":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("message", "Failed to turn relay on"),
        )
    return {"status": "success", "state": result.get("state")}

@router.post("/{relay_id}/state/off", dependencies=[Depends(require_role(["admin", "user"]))])
async def turn_relay_off(relay_id: str) -> dict:
    """
    Turn the specified relay OFF.
    """
    controller = get_controller(relay_id)
    result = await controller.turn_off()
    if result.get("status") != "success":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("message", "Failed to turn relay off"),
        )
    return {"status": "success", "state": result.get("state")}

@router.post("/{relay_id}/state/pulse", dependencies=[Depends(require_role(["admin", "user"]))])
async def pulse_relay(relay_id: str, request: Request) -> dict:
    """
    Pulse the specified relay by toggling its state for the stored pulse duration.
    The pulse operation is scheduled as an asyncio task so that the request returns immediately.
    """
    relay_config = next(
        (relay for relay in request.app.state.config.get("relays", []) if relay.get("id") == relay_id),
        None
    )
    if not relay_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relay with ID '{relay_id}' not found in configuration."
        )
    pulse_time = relay_config.get("pulse_time", 5)
    controller = get_controller(relay_id)
    initial_state = controller.state
    asyncio.create_task(_pulse(controller, pulse_time))
    return {
        "status": "success",
        "duration": pulse_time,
        "state": initial_state,
    }

@router.get("/relays/state", dependencies=[Depends(require_role(["admin", "user"]))])
async def get_all_relay_states(request: Request) -> dict:
    """
    Retrieve the current state of all relays.
    """
    try:
        states = {}
        for relay in request.app.state.config.get("relays", []):
            relay_id = relay.get("id")
            if relay_id:
                controller = get_controller(relay_id)
                states[relay_id] = controller.state
        return states
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
    
@router.get("/relays/enabled/state")
async def enabled_relay_states(request: Request) -> dict:
    """
    Retrieve the current state of all enabled relays.
    Enabled is a boolean and is set in the config file for each relay object as "enabled".
    """
    enabled_relays = [
        relay for relay in request.app.state.config.get("relays", [])
        if relay.get("enabled", False)
    ]
    states = {}
    for relay in enabled_relays:
        relay_id = relay.get("id")
        if relay_id:
            controller = get_controller(relay_id)
            states[relay_id] = controller.state
    return states
