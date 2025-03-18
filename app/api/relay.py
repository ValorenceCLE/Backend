import asyncio
from fastapi import APIRouter, HTTPException, status, BackgroundTasks, Body
from app.services.controller import RelayControl

router = APIRouter(prefix="/io", tags=["Relay API"])

def get_controller(relay_id: str) -> RelayControl:
    """
    Instantiate a RelayControl for the given relay_id, handling errors.
    """
    try:
        return RelayControl(relay_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )

async def _pulse(controller: RelayControl, pulse_time: int) -> None:
    """
    Toggle the relay state to start the pulse, wait for the specified duration,
    then toggle again to restore the original state.
    """
    try:
        await controller.toggle()
        await asyncio.sleep(pulse_time)
        await controller.toggle()
    except Exception as e:
        # Log or handle errors appropriately.
        pass

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

@router.post("/{relay_id}/state/off")
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

@router.post("/{relay_id}/state/pulse")
async def pulse_relay(
    relay_id: str,
    background_tasks: BackgroundTasks,
    pulse_time: int = Body(..., embed=True, description="Pulse duration in seconds")
) -> dict:
    """
    Pulse the specified relay by toggling its state for a short duration.
    Uses the RelayControl's toggle() method to invert the state,
    waits for the specified duration, then toggles again to restore.
    The pulse operation runs in the background.
    """
    controller = get_controller(relay_id)
    initial_state = controller.state
    background_tasks.add_task(_pulse, controller, pulse_time)
    return {
        "status": "success",
        "pulse_time": pulse_time,
        "initial_state": initial_state,
    }
