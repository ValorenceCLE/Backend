from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, status
import asyncio
import logging
from typing import Optional
from app.services.smbus import INA260Sensor, SHT30Sensor
from app.utils.dependencies import verify_token_ws
from app.utils.websocket_utils import (
    ws_manager, 
    websocket_connection, 
    safe_send_json, 
    safe_send_text, 
    safe_close
)

router = APIRouter(prefix="/sensor", tags=["sensors"])
logger = logging.getLogger(__name__)

# INA260 sensor configuration
INA260_CONFIG = {
    "relay_1": {"address": "0x44"},
    "relay_2": {"address": "0x45"},
    "relay_3": {"address": "0x46"},
    "relay_4": {"address": "0x47"},
    "relay_5": {"address": "0x48"},
    "relay_6": {"address": "0x49"},
    "main": {"address": "0x4B"},
}

class SensorFactory:
    """Factory for creating and caching sensor instances"""
    
    @staticmethod
    def create_ina260_sensor(relay_id: str) -> Optional[INA260Sensor]:
        """Create or retrieve a cached INA260 sensor instance"""
        if relay_id not in INA260_CONFIG:
            logger.error(f"No configuration found for relay ID: {relay_id}")
            return None
            
        cache_key = f"ina260_{relay_id}"
        sensor = ws_manager.get_resource(cache_key)
        
        if not sensor:
            try:
                address = int(INA260_CONFIG[relay_id]["address"], 16)
                sensor = INA260Sensor(address)
                ws_manager.store_resource(cache_key, sensor)
                logger.info(f"Created new INA260 sensor for {relay_id} at {INA260_CONFIG[relay_id]['address']}")
            except Exception as e:
                logger.error(f"Failed to create INA260 sensor for {relay_id}: {e}")
                return None
                
        return sensor
    
    @staticmethod
    def create_sht30_sensor() -> Optional[SHT30Sensor]:
        """Create or retrieve a cached SHT30 sensor instance"""
        cache_key = "sht30_sensor"
        sensor = ws_manager.get_resource(cache_key)
        
        if not sensor:
            try:
                sensor = SHT30Sensor()
                ws_manager.store_resource(cache_key, sensor)
                logger.info("Created new SHT30 sensor")
            except Exception as e:
                logger.error(f"Failed to create SHT30 sensor: {e}")
                return None
                
        return sensor

async def handle_authentication(websocket: WebSocket, token: str) -> bool:
    """Handle optional token authentication for sensor WebSockets"""
    if token:
        try:
            await verify_token_ws(token)
        except HTTPException as e:
            await safe_send_text(websocket, f"Authentication failed: {e.detail}")
            await safe_close(websocket, code=status.WS_1008_POLICY_VIOLATION)
            return False
    return True

async def sensor_data_loop(
    websocket: WebSocket,
    sensor_read_func,
    interval_ms: int,
    connection_id: str,
    error_prefix: str
) -> None:
    """
    Generic sensor data streaming loop with error handling
    
    Args:
        websocket: The WebSocket connection
        sensor_read_func: Async function to read sensor data
        interval_ms: Update interval in milliseconds
        connection_id: Identifier for this connection
        error_prefix: Prefix for error messages
    """
    sleep_interval = interval_ms / 1000  # Convert ms to seconds
    consecutive_errors = 0
    max_errors = 5
    
    logger.info(f"Starting sensor data stream for {connection_id} with {interval_ms}ms interval")
    
    try:
        while True:
            try:
                # Read sensor with timeout protection
                data = await asyncio.wait_for(
                    sensor_read_func(),
                    timeout=min(sleep_interval * 0.8, 0.5)  # Timeout slightly less than interval
                )
                
                if data is not None:
                    # Send data to client
                    if not await safe_send_json(websocket, data):
                        # Connection is closed, exit loop
                        break
                    consecutive_errors = 0
                else:
                    consecutive_errors += 1
                    logger.warning(f"Empty data for {connection_id}, error count: {consecutive_errors}")
                    if consecutive_errors >= max_errors:
                        await safe_send_text(websocket, f"Too many empty readings from {error_prefix}")
                        break
                
            except asyncio.TimeoutError:
                consecutive_errors += 1
                logger.warning(f"Timeout reading from {connection_id}, error count: {consecutive_errors}")
                if consecutive_errors >= max_errors:
                    await safe_send_text(websocket, f"{error_prefix} communication timeout")
                    break
                    
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error reading from {connection_id}: {e}")
                if consecutive_errors >= max_errors:
                    # Try to send error message, if it fails just exit
                    await safe_send_text(websocket, f"Disconnecting due to errors")
                    break
            
            # Wait for the next interval
            await asyncio.sleep(sleep_interval)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {connection_id}")
    except Exception as e:
        logger.exception(f"Unhandled error in websocket for {connection_id}: {e}")

@router.websocket("/ina260/{relay_id}")
async def sensor_voltage(
    websocket: WebSocket, 
    relay_id: str, 
    token: str = Query(None),
    interval: int = Query(1000, ge=100, le=10000)
):
    """
    WebSocket endpoint to stream INA260 sensor data for a given relay_id.
    
    Args:
        websocket: The WebSocket connection
        relay_id: Relay ID for the sensor to read
        token: Optional authentication token
        interval: Update interval in milliseconds (default: 1000ms)
    """
    connection_id = f"ina260_{relay_id}"
    
    # Define connection initialization
    async def on_connect(ws):
        # Authenticate if token provided
        if not await handle_authentication(ws, token):
            return False
            
        # Validate relay_id exists
        if relay_id not in INA260_CONFIG:
            await safe_send_text(ws, f"Unknown relay ID: {relay_id}")
            return False
            
        return True
    
    # Use the websocket_connection context manager
    async with websocket_connection(
        websocket, 
        ws_manager, 
        connection_id, 
        on_connect=on_connect
    ) as connected:
        # Exit if connection failed
        if not connected:
            return
        
        # Get or create the sensor
        sensor = SensorFactory.create_ina260_sensor(relay_id)
        if not sensor:
            await safe_send_text(websocket, f"Failed to initialize sensor for relay {relay_id}")
            await safe_close(websocket)
            return
        
        # Start the sensor data loop
        await sensor_data_loop(
            websocket,
            sensor.read_all,
            interval,
            connection_id,
            f"Sensor {relay_id}"
        )

@router.websocket("/sht30/environmental")
async def sensor_env(
    websocket: WebSocket,
    token: str = Query(None),
    interval: int = Query(1000, ge=100, le=10000)
):
    """
    WebSocket endpoint to stream SHT30 environmental sensor data.
    
    Args:
        websocket: The WebSocket connection
        token: Optional authentication token
        interval: Update interval in milliseconds (default: 1000ms)
    """
    connection_id = "sht30_env"
    
    # Define connection initialization
    async def on_connect(ws):
        # Authenticate if token provided
        if not await handle_authentication(ws, token):
            return False
        return True
    
    # Use the websocket_connection context manager
    async with websocket_connection(
        websocket, 
        ws_manager, 
        connection_id, 
        on_connect=on_connect
    ) as connected:
        # Exit if connection failed
        if not connected:
            return
        
        # Get or create the sensor
        sensor = SensorFactory.create_sht30_sensor()
        if not sensor:
            await safe_send_text(websocket, "Failed to initialize SHT30 sensor")
            await safe_close(websocket)
            return
        
        # Reset the sensor before starting
        try:
            await asyncio.wait_for(sensor.reset(), timeout=2.0)
            logger.info("SHT30 sensor reset successful")
        except Exception as e:
            logger.error(f"Error resetting SHT30 sensor: {e}")
            await safe_send_text(websocket, f"Error initializing sensor: {str(e)}")
            await safe_close(websocket)
            return
        
        # Start the sensor data loop
        await sensor_data_loop(
            websocket,
            sensor.read_all,
            interval,
            connection_id,
            "SHT30 sensor"
        )