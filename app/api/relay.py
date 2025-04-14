import asyncio
import logging
from fastapi import APIRouter, HTTPException, status, Request, Depends
from app.services.controller import RelayControl
from app.utils.internal_or_user import internal_or_user_auth  # Use the combined dependency

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(
    prefix="/io",
    tags=["Relay API"]
)

# Global lock for pulse operations to prevent race conditions
relay_lock = asyncio.Lock()

async def get_controller(relay_id: str) -> RelayControl:
    try:
        return await asyncio.to_thread(RelayControl, relay_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )

async def _pulse(controller: RelayControl, pulse_time) -> None:
    async with relay_lock:
        try:
            await controller.toggle()
            await asyncio.sleep(pulse_time)
            await controller.toggle()
        except Exception as e:
            logger.exception(f"Error during pulse operation for relay '{controller.id}': {e}")

# Use the combined dependency for authentication.
@router.post("/{relay_id}/state/on", dependencies=[Depends(internal_or_user_auth)])
async def turn_relay_on(relay_id: str) -> dict:
    controller = await get_controller(relay_id)
    result = await controller.turn_on()
    if result.get("status") != "success":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("message", "Failed to turn relay on"),
        )
    return {"status": "success", "state": result.get("state")}

@router.post("/{relay_id}/state/off", dependencies=[Depends(internal_or_user_auth)])
async def turn_relay_off(relay_id: str) -> dict:
    controller = await get_controller(relay_id)
    result = await controller.turn_off()
    if result.get("status") != "success":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("message", "Failed to turn relay off"),
        )
    return {"status": "success", "state": result.get("state")}

@router.post("/{relay_id}/state/pulse", dependencies=[Depends(internal_or_user_auth)])
async def pulse_relay(relay_id: str, request: Request) -> dict:
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
    controller = await get_controller(relay_id)
    initial_state = controller.state

    asyncio.create_task(_pulse(controller, pulse_time))

    return {
        "status": "success",
        "duration": pulse_time,
        "state": initial_state,
    }

@router.get("/relays/state", dependencies=[Depends(internal_or_user_auth)])
async def get_all_relay_states(request: Request) -> dict:
    try:
        relays = request.app.state.config.get("relays", [])
        states = {relay.get("id"): (await get_controller(relay.get("id"))).state for relay in relays if relay.get("id")}
        return states
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )

@router.get("/relays/enabled/state", dependencies=[Depends(internal_or_user_auth)])
async def enabled_relay_states(request: Request) -> dict:
    enabled_relays = [relay for relay in request.app.state.config.get("relays", []) if relay.get("enabled", False)]
    states = {relay.get("id"): (await get_controller(relay.get("id"))).state for relay in enabled_relays if relay.get("id")}
    return states
