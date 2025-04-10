from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException, status
import asyncio
import logging
from typing import Dict, List, Optional
from app.services.smbus import INA260Sensor, SHT30Sensor
from app.utils.dependencies import verify_token_ws

router = APIRouter(prefix="/sensor", tags=["sensors"])
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Connection manager to track active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.sensor_instances: Dict[str, object] = {}
    
    def register_connection(self, key: str, websocket: WebSocket):
        if key not in self.active_connections:
            self.active_connections[key] = []
        self.active_connections[key].append(websocket)
        logger.debug(f"Registered connection for {key}, total: {len(self.active_connections[key])}")
    
    def unregister_connection(self, key: str, websocket: WebSocket):
        if key in self.active_connections:
            try:
                self.active_connections[key].remove(websocket)
                logger.debug(f"Unregistered connection for {key}, remaining: {len(self.active_connections[key])}")
            except ValueError:
                pass
    
    def get_sensor(self, sensor_type: str, sensor_id: str, **kwargs):
        """Get or create a sensor instance"""
        cache_key = f"{sensor_type}_{sensor_id}"
        
        if cache_key not in self.sensor_instances:
            if sensor_type == "ina260":
                address = int(kwargs.get("address", "0x0"), 16)
                self.sensor_instances[cache_key] = INA260Sensor(address)
            elif sensor_type == "sht30":
                self.sensor_instances[cache_key] = SHT30Sensor()
        
        return self.sensor_instances.get(cache_key)

# Singleton connection manager
manager = ConnectionManager()

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

async def safe_send_json(websocket: WebSocket, data):
    """Send JSON data with proper error handling for closed connections"""
    try:
        await websocket.send_json(data)
        return True
    except RuntimeError as e:
        if "close message has been sent" in str(e):
            # Connection is already closed, no need to send more messages
            return False
        raise
    except Exception as e:
        logger.error(f"Error sending data: {e}")
        return False

async def safe_send_text(websocket: WebSocket, text: str):
    """Send text with proper error handling for closed connections"""
    try:
        await websocket.send_text(text)
        return True
    except RuntimeError as e:
        if "close message has been sent" in str(e):
            # Connection is already closed, no need to send more messages
            return False
        raise
    except Exception as e:
        logger.error(f"Error sending text: {e}")
        return False

async def safe_close(websocket: WebSocket, code=status.WS_1000_NORMAL_CLOSURE):
    """Close WebSocket with proper error handling"""
    try:
        await websocket.close(code=code)
        return True
    except Exception as e:
        logger.debug(f"Error closing websocket (likely already closed): {e}")
        return False

@router.websocket("/ina260/{relay_id}")
async def sensor_voltage(
    websocket: WebSocket, 
    relay_id: str, 
    token: str = Query(None),
    interval: int = Query(1000, ge=100, le=10000)
):
    """
    WebSocket endpoint to stream INA260 sensor data for a given relay_id.
    """
    connection_id = f"ina260_{relay_id}"
    is_connected = False
    
    try:
        # First accept the connection
        await websocket.accept()
        is_connected = True
        
        # Optional authentication check
        if token:
            try:
                await verify_token_ws(token)
            except HTTPException as e:
                await safe_send_text(websocket, f"Authentication failed: {e.detail}")
                await safe_close(websocket, code=status.WS_1008_POLICY_VIOLATION)
                return
        
        # Validate relay_id exists in configuration
        if relay_id not in INA260_CONFIG:
            await safe_send_text(websocket, f"Unknown relay ID: {relay_id}")
            await safe_close(websocket)
            return
        
        # Register connection
        manager.register_connection(connection_id, websocket)
        
        # Get or create sensor
        try:
            sensor = manager.get_sensor("ina260", relay_id, address=INA260_CONFIG[relay_id]["address"])
            if not sensor:
                await safe_send_text(websocket, f"Failed to initialize sensor for relay {relay_id}")
                await safe_close(websocket)
                return
            
            logger.info(f"Starting INA260 data stream for {relay_id} with {interval}ms interval")
        except Exception as e:
            logger.error(f"Error creating sensor for {relay_id}: {e}")
            await safe_send_text(websocket, f"Error initializing sensor: {str(e)}")
            await safe_close(websocket)
            return
        
        # Main data loop
        consecutive_errors = 0
        max_errors = 5
        sleep_interval = interval / 1000  # Convert ms to seconds
        
        while is_connected:
            try:
                # Read sensor with timeout protection
                data = await asyncio.wait_for(
                    sensor.read_all(),
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
                    logger.warning(f"Empty data from sensor {relay_id}, error count: {consecutive_errors}")
                    if consecutive_errors >= max_errors:
                        await safe_send_text(websocket, f"Too many empty readings from sensor {relay_id}")
                        break
                
            except asyncio.TimeoutError:
                consecutive_errors += 1
                logger.warning(f"Timeout reading from sensor {relay_id}, error count: {consecutive_errors}")
                if consecutive_errors >= max_errors:
                    await safe_send_text(websocket, f"Sensor {relay_id} communication timeout")
                    break
                    
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for {relay_id}")
                break
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error reading from sensor {relay_id}: {e}")
                if consecutive_errors >= max_errors:
                    # Try to send error message, if it fails just exit
                    await safe_send_text(websocket, f"Disconnecting due to errors")
                    break
            
            # Wait for the next interval
            await asyncio.sleep(sleep_interval)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {relay_id}")
    except Exception as e:
        logger.exception(f"Unhandled error in websocket for {relay_id}: {e}")
    finally:
        # Ensure connection is closed and cleaned up
        if is_connected:
            await safe_close(websocket)
        manager.unregister_connection(connection_id, websocket)
        logger.info(f"Closing INA260 data stream for {relay_id}")


@router.websocket("/sht30/environmental")
async def sensor_env(
    websocket: WebSocket,
    token: str = Query(None),
    interval: int = Query(1000, ge=100, le=10000)
):
    """
    WebSocket endpoint to stream SHT30 environmental sensor data.
    """
    connection_id = "sht30_env"
    is_connected = False
    
    try:
        # First accept the connection
        await websocket.accept()
        is_connected = True
        
        # Optional authentication check
        if token:
            try:
                await verify_token_ws(token)
            except HTTPException as e:
                await safe_send_text(websocket, f"Authentication failed: {e.detail}")
                await safe_close(websocket, code=status.WS_1008_POLICY_VIOLATION)
                return
        
        # Register connection
        manager.register_connection(connection_id, websocket)
        
        # Get or create sensor
        try:
            sensor = manager.get_sensor("sht30", "main")
            if not sensor:
                await safe_send_text(websocket, "Failed to initialize SHT30 sensor")
                await safe_close(websocket)
                return
            
            # Reset the sensor before starting
            try:
                await asyncio.wait_for(sensor.reset(), timeout=2.0)
            except Exception as e:
                logger.error(f"Error resetting SHT30 sensor: {e}")
                await safe_send_text(websocket, f"Error initializing sensor: {str(e)}")
                await safe_close(websocket)
                return
                
            logger.info(f"Starting SHT30 environmental data stream with {interval}ms interval")
        except Exception as e:
            logger.error(f"Error creating SHT30 sensor: {e}")
            await safe_send_text(websocket, f"Error initializing sensor: {str(e)}")
            await safe_close(websocket)
            return
        
        # Main data loop
        consecutive_errors = 0
        max_errors = 5
        sleep_interval = interval / 1000  # Convert ms to seconds
        
        while is_connected:
            try:
                # Read sensor with timeout protection
                data = await asyncio.wait_for(
                    sensor.read_all(),
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
                    logger.warning(f"Empty data from SHT30 sensor, error count: {consecutive_errors}")
                    if consecutive_errors >= max_errors:
                        await safe_send_text(websocket, "Too many empty readings from SHT30 sensor")
                        break
                
            except asyncio.TimeoutError:
                consecutive_errors += 1
                logger.warning(f"Timeout reading from SHT30 sensor, error count: {consecutive_errors}")
                if consecutive_errors >= max_errors:
                    await safe_send_text(websocket, "SHT30 sensor communication timeout")
                    break
                    
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected for SHT30 sensor")
                break
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error reading from SHT30 sensor: {e}")
                if consecutive_errors >= max_errors:
                    # Try to send error message, if it fails just exit
                    await safe_send_text(websocket, "Disconnecting due to errors")
                    break
            
            # Wait for the next interval
            await asyncio.sleep(sleep_interval)
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for SHT30 sensor")
    except Exception as e:
        logger.exception(f"Unhandled error in websocket for SHT30 sensor: {e}")
    finally:
        # Ensure connection is closed and cleaned up
        if is_connected:
            await safe_close(websocket)
        manager.unregister_connection(connection_id, websocket)
        logger.info("Closing SHT30 environmental data stream")