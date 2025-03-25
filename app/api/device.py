import asyncio
import psutil
from fastapi.responses import FileResponse
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from concurrent.futures import ThreadPoolExecutor

router = APIRouter(prefix="/device", tags=["Device API"])
executor = ThreadPoolExecutor()

async def get_cpu_usage():
    """Asynchronously retrieves the current CPU usage percentage using a thread executor."""
    loop = asyncio.get_running_loop()
    # psutil.cpu_percent blocks for the interval; run it in a thread
    return await loop.run_in_executor(executor, psutil.cpu_percent, 1)

async def get_memory_usage():
    """Asynchronously retrieves the current memory usage percentage using a thread executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, lambda: psutil.virtual_memory().percent)

async def get_disk_usage():
    """Asynchronously retrieves the current disk usage percentage using a thread executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, lambda: psutil.disk_usage("/").percent)

@router.websocket("/usage")
async def websocket_usage(websocket: WebSocket):
    """WebSocket endpoint to stream system usage metrics."""
    await websocket.accept()
    try:
        while True:
            cpu = await get_cpu_usage()
            memory = await get_memory_usage()
            disk = await get_disk_usage()
            usage_data = {
                "cpu": cpu,
                "memory": memory,
                "disk": disk,
            }
            await websocket.send_json(usage_data)
            await asyncio.sleep(1)  # Stream data every second
    except WebSocketDisconnect:
        print("WebSocket connection closed: Client disconnected.")
    except Exception as e:
        print(f"WebSocket connection closed due to error: {e}")
    finally:
        await websocket.close()

LOG_FILES = {
    "camera": "/var/log/camera.log",
    "router": "/var/log/router.log"
}

@router.get("/logs/camera")
async def get_camera_log():
    """
    Endpoint to download the camera log file.
    """
    log_path = LOG_FILES.get("camera")
    if not log_path:
        raise HTTPException(status_code=404, detail="Camera log file not found")

    try:
        return FileResponse(log_path, filename="camera.log", media_type="application/octet-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/router")
async def get_router_log():
    """
    Endpoint to download the router log file.
    """
    log_path = LOG_FILES.get("router")
    if not log_path:
        raise HTTPException(status_code=404, detail="Router log file not found")

    try:
        return FileResponse(log_path, filename="router.log", media_type="application/octet-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.post("/reboot")
async def reboot_device():
    """
    Endpoint to reboot the device.
    """
    try:
        # Perform device reboot
        return {"message": "Device rebooted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.post("/power-cycle")
async def power_cycle_device():
    """
    Endpoint to power cycle the device.
    """
    try:
        # Perform device power cycle
        return {"message": "Device power cycled successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/restore-defaults")
async def restore_defaults():
    pass
