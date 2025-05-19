import logging
from fastapi.responses import FileResponse
from fastapi import APIRouter, HTTPException, Depends, status
from concurrent.futures import ThreadPoolExecutor
import os
from app.utils.dependencies import require_role
from app.core.env_settings import env

router = APIRouter(prefix="/device", tags=["Device API"])
executor = ThreadPoolExecutor()
logger = logging.getLogger(__name__)

@router.get("/logs/camera", dependencies=[Depends(require_role("admin"))])
async def get_camera_log():
    """
    Endpoint to download the camera log file.
    """
    log_path = env.CAMERA_LOG_FILE
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
    log_path = env.ROUTER_LOG_FILE
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


