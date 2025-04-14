"""
WebSocket endpoints for real-time data streaming.

This module provides WebSocket endpoints for streaming real-time sensor data
and system metrics to connected clients.
"""
from fastapi import WebSocket, WebSocketDisconnect, Query, Depends, HTTPException, status
import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, Callable, Awaitable
from app.utils.dependencies import verify_token_ws
from app.utils.websocket_utils import (
    ws_manager, 
    websocket_connection, 
    safe_send_json, 
    safe_send_text, 
    safe_close)

logger = logging.getLogger(__name__)

# Task result tracking for sending to WebSocket clients
latest_sensor_data = {}

async def websocket_handler(
    websocket: WebSocket,
    data_source: str,
    token: str = None,
    interval: int = 1000
):
    """
    Generic WebSocket handler for streaming data.
    
    Args:
        websocket: The WebSocket connection
        data_source: Name of the data source to stream
        token: Optional authentication token
        interval: Update interval in milliseconds
    """
    connection_id = f"{data_source}_{id(websocket)}"
    
    # Define authentication handler
    async def on_connect(ws):
        # Authenticate if token provided
        if token:
            try:
                await verify_token_ws(token)
            except HTTPException as e:
                await safe_send_text(ws, f"Authentication failed: {e.detail}")
                await safe_close(ws, code=status.WS_1008_POLICY_VIOLATION)
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
        
        logger.info(f"Started WebSocket stream for {data_source}")
        
        # Calculate sleep time from interval
        sleep_seconds = interval / 1000
        
        try:
            while True:
                # Get the latest data for this source
                if data_source in latest_sensor_data:
                    data = latest_sensor_data[data_source]
                    
                    # Send data if available
                    if data:
                        if not await safe_send_json(websocket, data):
                            # Connection closed, exit loop
                            break
                
                # Wait for the next interval
                await asyncio.sleep(sleep_seconds)
                
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for {connection_id}")
        except Exception as e:
            logger.exception(f"Error in WebSocket stream for {connection_id}: {e}")

# WebSocket endpoint for relay power data
async def relay_power_websocket(
    websocket: WebSocket,
    relay_id: str,
    token: str = Query(None),
    interval: int = Query(1000, ge=100, le=10000)
):
    """WebSocket endpoint for streaming relay power data"""
    await websocket_handler(websocket, f"relay_{relay_id}", token, interval)

# WebSocket endpoint for environmental data
async def environmental_websocket(
    websocket: WebSocket,
    token: str = Query(None),
    interval: int = Query(1000, ge=100, le=10000)
):
    """WebSocket endpoint for streaming environmental sensor data"""
    await websocket_handler(websocket, "environmental", token, interval)

# WebSocket endpoint for system usage data
async def system_usage_websocket(
    websocket: WebSocket,
    token: str = Query(None),
    interval: int = Query(3000, ge=1000, le=10000)
):
    """WebSocket endpoint for streaming system usage metrics"""
    await websocket_handler(websocket, "system", token, interval)

# Function to update data from tasks
def update_sensor_data(source: str, data: Dict[str, Any]):
    """
    Update the latest sensor data for a source.
    
    This function is called from Celery tasks to provide data
    for WebSocket clients.
    """
    global latest_sensor_data
    latest_sensor_data[source] = data