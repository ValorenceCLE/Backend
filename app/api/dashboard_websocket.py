"""
Dashboard WebSocket endpoint for efficiently consolidating multiple data sources.

This module provides a single WebSocket endpoint that streams all dashboard
data (relay states, voltage, temperature) in a single connection.
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
from app.core.config import config_manager
from celery_app import app as celery_app
from app.services.smbus import INA260Sensor, SHT30Sensor

logger = logging.getLogger(__name__)

# Creating sensor instances for dashboard
async def create_sensors():
    """Create dashboard sensor instances"""
    sensors = {}
    try:
        # Main power sensor
        sensors["main_sensor"] = INA260Sensor(address=0x4B)
        
        # Environmental sensor
        sensors["env_sensor"] = SHT30Sensor()
        await sensors["env_sensor"].reset()
        
        return sensors
    except Exception as e:
        logger.error(f"Error creating dashboard sensors: {e}")
        return {}

async def dashboard_data_loop(websocket: WebSocket, interval_seconds: float = 2.0):
    """
    Main data loop that collects and sends all dashboard data.
    
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
        dashboard_data = {
            "relay_states": {},
            "sensors": {
                "main": {},
                "environmental": {}
            }
        }
        
        # Main loop
        while True:
            try:
                # 1. Get relay states
                config = config_manager.get_config()
                relay_ids = [relay.id for relay in config.relays if relay.enabled]
                
                if relay_ids:
                    task = celery_app.send_task(
                        'app.core.tasks.relay_tasks.get_all_relay_states',
                        args=[relay_ids],
                    )
                    relay_states = task.get(timeout=min(interval_seconds * 0.4, 2.0))
                    dashboard_data["relay_states"] = relay_states or {}
                
                # 2. Get main voltage sensor data
                if "main_sensor" in sensors:
                    main_data = await asyncio.wait_for(
                        sensors["main_sensor"].read_all(),
                        timeout=1.0
                    )
                    if main_data:
                        dashboard_data["sensors"]["main"] = main_data
                
                # 3. Get environmental sensor data
                if "env_sensor" in sensors:
                    env_data = await asyncio.wait_for(
                        sensors["env_sensor"].read_all(),
                        timeout=1.0
                    )
                    if env_data:
                        dashboard_data["sensors"]["environmental"] = env_data
                
                # Send the consolidated data to the client
                if not await safe_send_json(websocket, dashboard_data):
                    # Connection closed, exit loop
                    break
                
            except asyncio.TimeoutError:
                logger.warning("Timeout reading dashboard sensors")
            except Exception as e:
                logger.error(f"Error in dashboard data loop: {e}")
            
            # Wait for next interval
            await asyncio.sleep(interval_seconds)
            
    except WebSocketDisconnect:
        logger.info("Dashboard WebSocket disconnected")
    except Exception as e:
        logger.exception(f"Unhandled error in dashboard WebSocket: {e}")

async def dashboard_websocket(
    websocket: WebSocket,
    token: str = Query(None),
    interval: float = Query(2.0, ge=0.5, le=5.0)
):
    """WebSocket endpoint to stream all dashboard data in a single connection"""
    connection_id = f"dashboard_{id(websocket)}"
    
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
        
        logger.info(f"Started dashboard WebSocket with {interval}s interval")
        await dashboard_data_loop(websocket, interval_seconds=interval)