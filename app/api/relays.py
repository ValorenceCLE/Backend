import logging
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Depends, status, Request, Body
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

# Build a global dictionary of RelayController instances from the static hardware configuration.
RELAY_CONTROLLERS: Dict[str, RelayController] = {}
for relay_cfg in hardware.get("relays", []):
    relay_id = relay_cfg.get("relayId")
    if relay_id:
        RELAY_CONTROLLERS[relay_id] = RelayController(relay_cfg)


def update_dynamic_config(request: Request, relay_id: str, new_state: str) -> None:
    """
    Update the in-memory dynamic configuration stored in app.state.config for the given relay.
    Assumes that request.app.state.config.relays is an object keyed by relay IDs.
    """
    config = request.app.state.config
    if "relays" not in config:
        config["relays"] = {}
    # Update the specific relay
    if relay_id in config["relays"]:
        config["relays"][relay_id]["state"] = new_state
    else:
        # Find static info from hardware config for relay_id
        static_relay = next((r for r in hardware.get("relays", []) if r.get("relayId") == relay_id), {})
        # Use pulse_time from dynamic config if available; otherwise use static pulse_time.
        pulse_time = config.get("relays", {}).get(relay_id, {}).get("pulse_time", static_relay.get("pulse_time", 1))
        config["relays"][relay_id] = {
            "id": relay_id,
            "state": new_state,
            "pulse_time": pulse_time,
            # Include other dynamic fields as needed.
        }
    request.app.state.config = config


@router.get("/", dependencies=[Depends(is_authenticated)])
async def get_all_relays(request: Request) -> Dict[str, Any]:
    """
    GET /api/relays/
    
    Example Request:
      GET http://localhost:8000/api/relays/
      Headers: { Authorization: "Bearer <your_token>" }
    
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
async def turn_relays_on(request: Request, relay_ids: List[str] = Body(..., example=["relay_1", "relay_3"])) -> Dict[str, Any]:
    """
    POST /api/relays/on
    
    Example Request Body:
      [
        "relay_1",
        "relay_3"
      ]
    
    Turns on the specified relays.
    """
    results = {}
    if not relay_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Relay IDs must be provided in the request body.")
    for relay_id in relay_ids:
        controller = RELAY_CONTROLLERS.get(relay_id)
        if not controller:
            results[relay_id] = "Relay not found"
        else:
            try:
                await controller.turn_on()
                state = await controller.device_state()
                results[relay_id] = state
                update_dynamic_config(request, relay_id, state)
            except Exception as e:
                current_state = await controller.device_state()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={relay_id: {"error": str(e), "state": current_state}},
                )
    return results


@router.post("/off", dependencies=[Depends(is_authenticated)])
async def turn_relays_off(request: Request, relay_ids: List[str] = Body(..., example=["relay_2", "relay_4"])) -> Dict[str, Any]:
    """
    POST /api/relays/off
    
    Example Request Body:
      [
        "relay_2",
        "relay_4"
      ]
    
    Turns off the specified relays.
    """
    results = {}
    if not relay_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Relay IDs must be provided in the request body.")
    for relay_id in relay_ids:
        controller = RELAY_CONTROLLERS.get(relay_id)
        if not controller:
            results[relay_id] = "Relay not found"
        else:
            try:
                await controller.turn_off()
                state = await controller.device_state()
                results[relay_id] = state
                update_dynamic_config(request, relay_id, state)
            except Exception as e:
                current_state = await controller.device_state()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={relay_id: {"error": str(e), "state": current_state}},
                )
    return results


@router.post("/pulse", dependencies=[Depends(is_authenticated)])
async def pulse_relays(request: Request, relay_ids: List[str] = Body(..., example=["relay_3", "relay_5"])) -> Dict[str, Any]:
    """
    POST /api/relays/pulse
    
    Example Request Body:
      [
        "relay_3",
        "relay_5"
      ]
    
    Pulses the specified relays for their configured duration.
    The pulse duration is taken from the dynamic configuration (app.state.config) if available.
    """
    results = {}
    if not relay_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Relay IDs must be provided in the request body.")
    for relay_id in relay_ids:
        controller = RELAY_CONTROLLERS.get(relay_id)
        if not controller:
            results[relay_id] = "Relay not found"
        else:
            try:
                # Get dynamic pulse_time from app.state.config; fallback to controller's own pulse_time.
                dynamic_relay = request.app.state.config.get("relays", {}).get(relay_id, {})
                duration = dynamic_relay.get("pulse_time", controller.pulse_time)
                await controller.pulse(duration)
                state = await controller.device_state()
                results[relay_id] = state
                update_dynamic_config(request, relay_id, state)
            except Exception as e:
                current_state = await controller.device_state()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={relay_id: {"error": str(e), "state": current_state}},
                )
    return results


@router.get("/{relay_id}", dependencies=[Depends(is_authenticated)])
async def get_relay_state(relay_id: str, request: Request) -> Dict[str, Any]:
    """
    GET /api/relays/{relay_id}
    
    Example Request:
      GET http://localhost:8000/api/relays/relay_1
      Headers: { Authorization: "Bearer <your_token>" }
    
    Returns the state of the specified relay.
    """
    controller = RELAY_CONTROLLERS.get(relay_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Relay not found")
    try:
        state = await controller.device_state()
        update_dynamic_config(request, relay_id, state)
        return {"relayId": relay_id, "state": state}
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})


@router.post("/{relay_id}/on", dependencies=[Depends(is_authenticated)])
async def turn_single_relay_on(relay_id: str, request: Request) -> Dict[str, Any]:
    """
    POST /api/relays/{relay_id}/on
    
    Example Request:
      POST http://localhost:8000/api/relays/relay_1/on
      Headers: { Authorization: "Bearer <your_token>" }
    
    Turns on the specified relay.
    """
    controller = RELAY_CONTROLLERS.get(relay_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Relay not found")
    try:
        await controller.turn_on()
        state = await controller.device_state()
        update_dynamic_config(request, relay_id, state)
        return {"relayId": relay_id, "state": state}
    except Exception as e:
        current_state = await controller.device_state()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": str(e), "state": current_state})


@router.post("/{relay_id}/off", dependencies=[Depends(is_authenticated)])
async def turn_single_relay_off(relay_id: str, request: Request) -> Dict[str, Any]:
    """
    POST /api/relays/{relay_id}/off
    
    Example Request:
      POST http://localhost:8000/api/relays/relay_1/off
      Headers: { Authorization: "Bearer <your_token>" }
    
    Turns off the specified relay.
    """
    controller = RELAY_CONTROLLERS.get(relay_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Relay not found")
    try:
        await controller.turn_off()
        state = await controller.device_state()
        update_dynamic_config(request, relay_id, state)
        return {"relayId": relay_id, "state": state}
    except Exception as e:
        current_state = await controller.device_state()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": str(e), "state": current_state})


@router.post("/{relay_id}/pulse", dependencies=[Depends(is_authenticated)])
async def pulse_single_relay(relay_id: str, request: Request) -> Dict[str, Any]:
    """
    POST /api/relays/{relay_id}/pulse
    
    Example Request:
      POST http://localhost:8000/api/relays/relay_1/pulse
      Headers: { Authorization: "Bearer <your_token>" }
    
    Pulses the specified relay for its configured duration.
    """
    controller = RELAY_CONTROLLERS.get(relay_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Relay not found")
    try:
        # Get dynamic pulse_time from app.state.config if available.
        dynamic_relay = request.app.state.config.get("relays", {}).get(relay_id, {})
        duration = dynamic_relay.get("pulse_time", controller.pulse_time)
        await controller.pulse(duration)
        state = await controller.device_state()
        update_dynamic_config(request, relay_id, state)
        return {"relayId": relay_id, "state": state}
    except Exception as e:
        current_state = await controller.device_state()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": str(e), "state": current_state})
