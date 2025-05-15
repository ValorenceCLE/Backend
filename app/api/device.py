import asyncio
import psutil
import logging
from fastapi.responses import FileResponse
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query, status
from concurrent.futures import ThreadPoolExecutor
import os
from app.utils.dependencies import require_role, verify_token_ws
from app.utils.websocket_utils import (
    ws_manager, 
    websocket_connection, 
    safe_send_json, 
    safe_send_text, 
    safe_close
)
import subprocess

router = APIRouter(prefix="/device", tags=["Device API"])
executor = ThreadPoolExecutor()
logger = logging.getLogger(__name__)

async def get_cpu_usage():
    """Asynchronously retrieves the current CPU usage percentage using a thread executor."""
    loop = asyncio.get_running_loop()
    # Use 0 interval to get immediate reading instead of waiting 1 second
    return await loop.run_in_executor(executor, psutil.cpu_percent, 0)

async def get_memory_usage():
    """Asynchronously retrieves the current memory usage percentage using a thread executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, lambda: psutil.virtual_memory().percent)

async def get_disk_usage():
    """Asynchronously retrieves the current disk usage percentage using a thread executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, lambda: psutil.disk_usage("/").percent)

async def handle_usage_authentication(websocket: WebSocket, token: str):
    """Handle optional WebSocket authentication for usage endpoint"""
    if token:
        try:
            await verify_token_ws(token)
        except HTTPException as e:
            await safe_send_text(websocket, f"Authentication failed: {e.detail}")
            await safe_close(websocket, code=status.WS_1008_POLICY_VIOLATION)
            return False
    return True

@router.websocket("/usage")
async def websocket_usage(
    websocket: WebSocket, 
    token: str = Query(None),
    interval: int = Query(3000, ge=1000, le=10000)
):
    """
    WebSocket endpoint to stream system usage metrics with optional authentication.
    
    Args:
        websocket: The WebSocket connection
        token: Optional authentication token
        interval: Update interval in milliseconds (default: 3000ms)
    """
    # Convert interval to seconds
    update_interval = interval / 3000
    connection_id = f"usage_{id(websocket)}"
    
    # Define authentication handler
    async def on_connect(ws):
        return await handle_usage_authentication(ws, token)
    
    # Use the websocket_connection context manager to handle the connection lifecycle
    async with websocket_connection(
        websocket, 
        ws_manager, 
        connection_id, 
        on_connect=on_connect
    ) as connected:
        # Exit if connection failed
        if not connected:
            return
            
        logger.info(f"Starting system usage stream with {interval}ms interval")
        
        try:
            consecutive_errors = 0
            max_errors = 3
            
            while True:
                try:
                    # Gather system metrics with timeout protection
                    usage_data = {
                        "cpu": await asyncio.wait_for(get_cpu_usage(), timeout=update_interval * 0.8),
                        "memory": await asyncio.wait_for(get_memory_usage(), timeout=update_interval * 0.8),
                        "disk": await asyncio.wait_for(get_disk_usage(), timeout=update_interval * 0.8),
                    }
                    
                    # Safely send data to the client
                    if not await safe_send_json(websocket, usage_data):
                        # Connection closed, exit loop
                        break
                        
                    # Reset error counter on success
                    consecutive_errors = 0
                        
                except asyncio.TimeoutError:
                    consecutive_errors += 1
                    logger.warning(f"Timeout gathering system metrics, error count: {consecutive_errors}")
                    if consecutive_errors >= max_errors:
                        await safe_send_text(websocket, "System metrics gathering timeout")
                        break
                        
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(f"Error gathering system metrics: {e}")
                    if consecutive_errors >= max_errors:
                        await safe_send_text(websocket, "Disconnecting due to persistent errors")
                        break
                
                # Wait for the next update interval
                await asyncio.sleep(update_interval)
                
        except WebSocketDisconnect:
            logger.info("WebSocket connection closed: Client disconnected")
        except Exception as e:
            logger.exception(f"Unhandled error in usage WebSocket: {e}")

# File locations for logs
LOG_FILES = {
    "camera": "/var/log/camera.log",
    "router": "/var/log/router.log"
}

@router.get("/logs/camera", dependencies=[Depends(require_role("admin"))])
async def get_camera_log():
    """
    Endpoint to download the camera log file.
    """
    log_path = LOG_FILES.get("camera")
    if not log_path or not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="Camera log file not found")

    try:
        return FileResponse(log_path, filename="camera.log", media_type="application/octet-stream")
    except Exception as e:
        logger.error(f"Error serving camera log file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/logs/router", dependencies=[Depends(require_role("admin"))])
async def get_router_log():
    """
    Endpoint to download the router log file.
    """
    log_path = LOG_FILES.get("router")
    if not log_path or not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="Router log file not found")

    try:
        return FileResponse(log_path, filename="router.log", media_type="application/octet-stream")
    except Exception as e:
        logger.error(f"Error serving router log file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reboot", dependencies=[Depends(require_role("admin"))])
async def reboot_system():
    """Reboot the Raspberry Pi CM5 using hardware watchdog"""
    try:
        logger.warning("System reboot requested via API using watchdog")
        
        # Check if watchdog device exists
        if not os.path.exists('/dev/watchdog'):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Watchdog device not available. Make sure it's enabled in the device tree."
            )
        
        # Open the watchdog device
        try:
            with open('/dev/watchdog', 'w') as wdt:
                # Writing a character other than 'V' and not closing properly
                # will trigger the watchdog to reboot the system
                wdt.write('X')
                # Don't close the file - this will trigger the watchdog
            
            # Return success before the system reboots
            return {"status": "success", "message": "Reboot initiated via watchdog timer"}
        except PermissionError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Permission denied when accessing watchdog. Check container privileges."
            )
            
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.exception(f"Failed to reboot system using watchdog: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reboot system: {str(e)}"
        )


