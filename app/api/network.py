import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query, BackgroundTasks
from fastapi.responses import StreamingResponse

import speedtest
from app.services.ping import (
    ping_hosts,
    is_host_online,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(
    prefix="/network",
    tags=["Network API"]
)

# --- In-memory cache ---
last_speedtest_time: Optional[datetime] = None
last_speedtest_result: Optional[dict] = None
MIN_SPEEDTEST_INTERVAL = 300  # 5 minutes between tests

# --- /ping (batch) ---
@router.get("/ping")
async def ping_endpoint(
    hosts: str = Query(..., description="Comma-separated hostnames/IPs"),
    retries: int = 2,
    timeout: int = 1,
    port: int = 80
):
    host_list = [h.strip() for h in hosts.split(",") if h.strip()]
    if not host_list:
        return {"error": "No valid hosts provided"}

    results, summary = await ping_hosts(host_list, retries=retries, timeout=timeout, fallback_port=port)
    return {
        "summary": summary,
        "results": results
    }

# --- /stream-ping (real-time via Server-Sent Events) ---
@router.get("/stream-ping")
async def stream_ping(host: str, interval: int = 2):
    async def event_stream():
        while True:
            result = await is_host_online(host, retries=1, timeout=1, fallback_port=80)
            yield f"data: {json.dumps(result)}\n\n"
            await asyncio.sleep(interval)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.get("/host/status")
async def host_online(
    host: str = Query(..., description="Hostname or IP address to check"),
    retries: int = 2,
    timeout: int = 1,
    port: int = 80
):
    result = await is_host_online(host, retries=retries, timeout=timeout, fallback_port=port)
    return result

# --- Asynchronous speedtest implementation ---
async def async_perform_speedtest():
    """Wraps the synchronous speedtest-cli in an asynchronous function"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_speedtest)

def _run_speedtest():
    """The synchronous part that runs in a thread pool"""
    try:
        s = speedtest.Speedtest(secure=True)
        # Get a list of servers then select best
        s.get_servers()
        s.get_best_server()
        
        # Run tests
        download_result = s.download()
        # Short delay to avoid rapid consecutive tests
        time.sleep(0.5)
        upload_result = s.upload()
        
        results = s.results.dict()
        logger.info(f"Speedtest completed successfully: {download_result/1000000:.2f} Mbps down, {upload_result/1000000:.2f} Mbps up")
        return results
    except speedtest.ConfigRetrievalError as e:
        logger.error(f"Speedtest configuration retrieval failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during speedtest: {e}")
        return None

@router.get("/speedtest")
async def speedtest_endpoint(force: bool = False, background_tasks: BackgroundTasks = None):
    global last_speedtest_time, last_speedtest_result
    
    current_time = datetime.now()
    
    # Return cached results if available and not forcing a new test
    if not force and last_speedtest_time and last_speedtest_result:
        seconds_since_last = (current_time - last_speedtest_time).total_seconds()
        if seconds_since_last < MIN_SPEEDTEST_INTERVAL:
            wait_time = MIN_SPEEDTEST_INTERVAL - seconds_since_last
            return {
                "cached": True,
                "message": f"Using cached result from {seconds_since_last:.0f} seconds ago. Next test available in {wait_time:.0f} seconds. Use force=true to override.",
                "results": last_speedtest_result
            }
    
    # If we want background processing (non-blocking)
    if background_tasks:
        # If a test is already running, return status
        if last_speedtest_time and (current_time - last_speedtest_time).total_seconds() < 30:
            return {"status": "A speedtest is already in progress. Please try again in a few moments."}
            
        # Start a new test in the background
        background_tasks.add_task(_background_speedtest_task)
        return {"status": "Speedtest started in background. Results will be cached for the next request."}
    
    # Synchronous (blocking) request - run the test now
    try:
        results = await async_perform_speedtest()
        
        if results:
            last_speedtest_time = current_time
            last_speedtest_result = results
            return {
                "cached": False,
                "results": results
            }
        else:
            return {"error": "Speedtest failed, please try again later"}
    except Exception as e:
        logger.error(f"Error in speedtest endpoint: {e}")
        return {"error": f"Speedtest failed: {str(e)}"}

async def _background_speedtest_task():
    """Task to run a speedtest in the background and cache the results"""
    global last_speedtest_time, last_speedtest_result
    
    try:
        results = await async_perform_speedtest()
        if results:
            last_speedtest_time = datetime.now()
            last_speedtest_result = results
            logger.info("Background speedtest completed successfully")
        else:
            logger.error("Background speedtest failed")
    except Exception as e:
        logger.error(f"Error in background speedtest task: {e}")