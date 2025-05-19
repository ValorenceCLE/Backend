"""
Settings WebSocket endpoint for consolidating system data.

This module provides a single WebSocket endpoint that streams all settings
data (system usage, camera voltage, router voltage) in a single connection.
"""
import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect, Query
from app.utils.websocket_utils import (
    ws_manager,
    websocket_connection,
    safe_send_json,
    safe_close
)
from app.utils.dependencies import verify_token_ws
from app.services.smbus import INA260Sensor

logger = logging.getLogger(__name__)

# Creating sensor instances for settings page
async def create_sensors():
    """Create settings page sensor instances"""
    sensors = {}
    try:
        # Camera voltage sensor (relay_1)
        sensors["camera_sensor"] = INA260Sensor(address=0x44)
        
        # Router voltage sensor (relay_2)
        sensors["router_sensor"] = INA260Sensor(address=0x45)
        
        return sensors
    except Exception as e:
        logger.error(f"Error creating settings sensors: {e}")
        return {}

async def get_system_usage():
    """Get system CPU, memory and disk usage"""
    try:
        import psutil
        
        # Use a thread executor for these operations
        loop = asyncio.get_running_loop()
        
        # Get CPU usage (0 interval to get immediate reading)
        cpu = await loop.run_in_executor(None, psutil.cpu_percent, 0)
        
        # Get memory usage
        memory = await loop.run_in_executor(None, lambda: psutil.virtual_memory().percent)
        
        # Get disk usage
        disk = await loop.run_in_executor(None, lambda: psutil.disk_usage("/").percent)
        
        return {
            "cpu": cpu,
            "memory": memory,
            "disk": disk
        }
    except Exception as e:
        logger.error(f"Error getting system usage: {e}")
        return {"cpu": 0, "memory": 0, "disk": 0}

async def settings_data_loop(websocket: WebSocket, interval_seconds: float = 2.0):
    """
    Main data loop that collects and sends all settings data.
    
    Args:
        websocket: The WebSocket connection
        interval_seconds: Update interval in seconds
    """
    try:
        # Create sensors
        sensors = await create_sensors()
        if not sensors:
            await safe_close(websocket)
            return
        
        # Data structure to send to client
        settings_data = {
            "usage": {"cpu": 0, "memory": 0, "disk": 0},
            "voltages": {
                "camera": 0,
                "router": 0
            }
        }
        
        # Main loop
        while True:
            try:
                # 1. Get system usage metrics
                usage_data = await get_system_usage()
                settings_data["usage"] = usage_data
                
                # 2. Get camera voltage
                if "camera_sensor" in sensors:
                    camera_data = await asyncio.wait_for(
                        sensors["camera_sensor"].read_voltage(),
                        timeout=1.0
                    )
                    if camera_data is not None:
                        settings_data["voltages"]["camera"] = camera_data
                
                # 3. Get router voltage
                if "router_sensor" in sensors:
                    router_data = await asyncio.wait_for(
                        sensors["router_sensor"].read_voltage(),
                        timeout=1.0
                    )
                    if router_data is not None:
                        settings_data["voltages"]["router"] = router_data
                
                # Send the consolidated data to the client
                if not await safe_send_json(websocket, settings_data):
                    # Connection closed, exit loop
                    break
                
            except asyncio.TimeoutError:
                logger.warning("Timeout reading settings sensors")
            except Exception as e:
                logger.error(f"Error in settings data loop: {e}")
            
            # Wait for next interval
            await asyncio.sleep(interval_seconds)
            
    except WebSocketDisconnect:
        logger.info("Settings WebSocket disconnected")
    except Exception as e:
        logger.exception(f"Unhandled error in settings WebSocket: {e}")

async def settings_websocket(
    websocket: WebSocket,
    token: str = Query(None),
    interval: float = Query(2.0, ge=0.5, le=5.0)
):
    """WebSocket endpoint to stream all settings data in a single connection"""
    connection_id = f"settings_{id(websocket)}"
    
    # Define authentication handler
    async def on_connect(ws):
        # Authenticate if token provided
        if token:
            try:
                await verify_token_ws(token)
            except Exception as e:
                logger.error(f"Authentication failed: {e}")
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
        
        logger.info(f"Started settings WebSocket with {interval}s interval")
        await settings_data_loop(websocket, interval_seconds=interval)