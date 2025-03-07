import logging
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Depends, status, Body
try:
    from app.utils.dependencies import is_authenticated
    from app.services.relay_controller import RelayController
    from app.config.hardware_config import hardware
except ImportError:
    from utils.dependencies import is_authenticated
    from services.relay_controller import RelayController
    from config.hardware_config import hardware

router = APIRouter(prefix="/relays", tags=["Relay Configuration API"])
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Build a global dictionary of RelayController instances using the hardware config.
RELAY_CONTROLLERS: Dict[str, RelayController] = {}
for relay_cfg in hardware.get("relays", []):
    relay_id = relay_cfg.get("relayId")
    if relay_id:
        RELAY_CONTROLLERS[relay_id] = RelayController(relay_cfg)


@router.get("/", dependencies=[Depends(is_authenticated)])
async def get_all_relays() -> Dict[str, Any]:
    """
    GET /api/relays/
    
    Example Request:
    GET http://localhost:8000/api/relays/
    Headers:
      Authorization: Bearer <your_token>
    
    Returns the state of all relays.
    """
    results = {}
    for relay_id, controller in RELAY_CONTROLLERS.items():
        try:
            state = await controller.device_state()
            results[relay_id] = state
        except Exception as e:
            results[relay_id] = f"Error: {str(e)}"
    return results


@router.post("/on", dependencies=[Depends(is_authenticated)])
async def turn_relays_on(relay_ids: List[str] = Body(..., example=["relay_1", "relay_3"])) -> Dict[str, Any]:
    """
    POST /api/relays/on
    
    Example Request Body:
    [
      "relay_1",
      "relay_3"
    ]
    
    Example Request:
    POST http://localhost:8000/api/relays/on
    Headers:
      Content-Type: application/json
      Authorization: Bearer <your_token>
    
    Turns on the specified relays.
    """
    results = {}
    if not relay_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Relay IDs must be provided in the request body."
        )
    for relay_id in relay_ids:
        controller = RELAY_CONTROLLERS.get(relay_id)
        if not controller:
            results[relay_id] = "Relay not found"
        else:
            try:
                await controller.turn_on()
                state = await controller.device_state()
                results[relay_id] = state
            except Exception as e:
                current_state = await controller.device_state()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={relay_id: {"error": str(e), "state": current_state}},
                )
    return results


@router.post("/off", dependencies=[Depends(is_authenticated)])
async def turn_relays_off(relay_ids: List[str] = Body(..., example=["relay_2", "relay_4"])) -> Dict[str, Any]:
    """
    POST /api/relays/off
    
    Example Request Body:
    [
      "relay_2",
      "relay_4"
    ]
    
    Example Request:
    POST http://localhost:8000/api/relays/off
    Headers:
      Content-Type: application/json
      Authorization: Bearer <your_token>
    
    Turns off the specified relays.
    """
    results = {}
    if not relay_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Relay IDs must be provided in the request body."
        )
    for relay_id in relay_ids:
        controller = RELAY_CONTROLLERS.get(relay_id)
        if not controller:
            results[relay_id] = "Relay not found"
        else:
            try:
                await controller.turn_off()
                state = await controller.device_state()
                results[relay_id] = state
            except Exception as e:
                current_state = await controller.device_state()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={relay_id: {"error": str(e), "state": current_state}},
                )
    return results


@router.post("/pulse", dependencies=[Depends(is_authenticated)])
async def pulse_relays(relay_ids: List[str] = Body(..., example=["relay_3", "relay_5"])) -> Dict[str, Any]:
    """
    POST /api/relays/pulse
    
    Example Request Body:
    [
      "relay_3",
      "relay_5"
    ]
    
    Example Request:
    POST http://localhost:8000/api/relays/pulse
    Headers:
      Content-Type: application/json
      Authorization: Bearer <your_token>
    
    Pulses the specified relays for their configured duration.
    """
    results = {}
    if not relay_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Relay IDs must be provided in the request body."
        )
    for relay_id in relay_ids:
        controller = RELAY_CONTROLLERS.get(relay_id)
        if not controller:
            results[relay_id] = "Relay not found"
        else:
            try:
                await controller.pulse()
                state = await controller.device_state()
                results[relay_id] = state
            except Exception as e:
                current_state = await controller.device_state()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={relay_id: {"error": str(e), "state": current_state}},
                )
    return results


@router.get("/{relay_id}", dependencies=[Depends(is_authenticated)])
async def get_relay_state(relay_id: str) -> Dict[str, Any]:
    """
    GET /api/relays/{relay_id}
    
    Example Request:
    GET http://localhost:8000/api/relays/relay_1
    Headers:
      Authorization: Bearer <your_token>
    
    Returns the state of the specified relay.
    """
    controller = RELAY_CONTROLLERS.get(relay_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Relay not found")
    try:
        state = await controller.device_state()
        return {"relayId": relay_id, "state": state}
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})


@router.post("/{relay_id}/on", dependencies=[Depends(is_authenticated)])
async def turn_single_relay_on(relay_id: str) -> Dict[str, Any]:
    """
    POST /api/relays/{relay_id}/on
    
    Example Request:
    POST http://localhost:8000/api/relays/relay_1/on
    Headers:
      Authorization: Bearer <your_token>
    
    Turns on the specified relay.
    """
    controller = RELAY_CONTROLLERS.get(relay_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Relay not found")
    try:
        await controller.turn_on()
        state = await controller.device_state()
        return {"relayId": relay_id, "state": state}
    except Exception as e:
        current_state = await controller.device_state()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(e), "state": current_state},
        )


@router.post("/{relay_id}/off", dependencies=[Depends(is_authenticated)])
async def turn_single_relay_off(relay_id: str) -> Dict[str, Any]:
    """
    POST /api/relays/{relay_id}/off
    
    Example Request:
    POST http://localhost:8000/api/relays/relay_1/off
    Headers:
      Authorization: Bearer <your_token>
    
    Turns off the specified relay.
    """
    controller = RELAY_CONTROLLERS.get(relay_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Relay not found")
    try:
        await controller.turn_off()
        state = await controller.device_state()
        return {"relayId": relay_id, "state": state}
    except Exception as e:
        current_state = await controller.device_state()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(e), "state": current_state},
        )


@router.post("/{relay_id}/pulse", dependencies=[Depends(is_authenticated)])
async def pulse_single_relay(relay_id: str) -> Dict[str, Any]:
    """
    POST /api/relays/{relay_id}/pulse
    
    Example Request:
    POST http://localhost:8000/api/relays/relay_1/pulse
    Headers:
      Authorization: Bearer <your_token>
    
    Pulses the specified relay for its configured duration.
    """
    controller = RELAY_CONTROLLERS.get(relay_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Relay not found")
    try:
        await controller.pulse()
        state = await controller.device_state()
        return {"relayId": relay_id, "state": state}
    except Exception as e:
        current_state = await controller.device_state()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(e), "state": current_state},
        )
