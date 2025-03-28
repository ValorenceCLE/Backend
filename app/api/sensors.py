from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import logging
from app.services.smbus import INA260Sensor, SHT30Sensor  # Adjust import paths as needed

router = APIRouter(prefix="/sensor", tags=["sensors"])
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Updated configuration key from "inn260_sensors" to "ina260_sensors"
CONFIG = {
    "ina260_sensors": [
        {"id": "relay_1", "sensor": "ina260_1", "address": "0x44"},
        {"id": "relay_2", "sensor": "ina260_2", "address": "0x45"},
        {"id": "relay_3", "sensor": "ina260_3", "address": "0x46"},
        {"id": "relay_4", "sensor": "ina260_4", "address": "0x47"},
        {"id": "relay_5", "sensor": "ina260_5", "address": "0x48"},
        {"id": "relay_6", "sensor": "ina260_6", "address": "0x49"},
        {"id": "main", "sensor": "ina260_7", "address": "0x4B"},
    ]
}

def get_ina260_config(relay_id: str):
    """
    Looks up the INA260 sensor configuration based on the provided relay ID.
    Returns the sensor configuration dict or None if not found.
    """
    for sensor in CONFIG.get("ina260_sensors", []):
        if sensor.get("id") == relay_id:
            return sensor
    return None

@router.websocket("/ina260/{relay_id}")
async def sensor_voltage(websocket: WebSocket, relay_id: str):
    """
    WebSocket endpoint to stream INA260 sensor data for a given relay_id.
    """
    await websocket.accept()
    # Look up sensor configuration based on relay_id.
    sensor_config = get_ina260_config(relay_id)
    if sensor_config is None:
        await websocket.send_text(f"No sensor configuration found for relay id: {relay_id}")
        await websocket.close()
        return

    try:
        # Create an INA260Sensor instance using the sensor's address.
        # Convert the hex string address to an integer.
        address = int(sensor_config["address"], 16)
        sensor = INA260Sensor(address)
        logger.info(f"Starting sensor voltage stream for relay {relay_id} on address {hex(address)}")

        while True:
            # Read sensor voltage.
            data = await sensor.read_all()
            if data is not None:
                await websocket.send_json(data)
            else:
                await websocket.send_text("Error reading sensor data.")
            # Sleep for a short interval before reading again.
            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for relay id: {relay_id}")
    except Exception as e:
        logger.exception(f"Error in websocket for relay id {relay_id}: {e}")
        await websocket.close()



@router.websocket("/sht30/environmental")
async def sensor_env(websocket: WebSocket):
    """
    WebSocket endpoint to stream SHT30 sensor data for temperature.
    """
    await websocket.accept()
    try:
        # Create an SHT30Sensor instance.
        sensor = SHT30Sensor()
        # Reset the sensor before starting to read data.
        await sensor.reset()
        logger.info("Starting SHT30 temperature stream.")

        while True:
            # Asynchronously get temperature data.
            data = await sensor.read_all()
            if data is not None:
                await websocket.send_json(data)
            else:
                await websocket.send_text("Error reading sensor data.")
            # Sleep for a short interval before reading again.
            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for temperature sensor.")
    except Exception as e:
        logger.exception(f"Error in websocket for temperature sensor: {e}")
        await websocket.close()

