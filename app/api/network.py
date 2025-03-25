import asyncio
import json
import logging
from typing import Dict
from fastapi import APIRouter, Query, Depends
from fastapi.responses import StreamingResponse
from app.utils.dependencies import is_authenticated
import speedtest
from app.services.ping import (
    ping_hosts,
    is_host_online,
)

# Optional Redis cache (comment out if not using Redis)
# import redis.asyncio as redis
# redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(
    prefix="/network",
    tags=["Network API"]
)

# --- In-memory task registry ---
ping_tasks: Dict[str, asyncio.Task] = {}

# --- /ping (batch) ---
@router.get("/ping", dependencies=[Depends(is_authenticated)])
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
@router.get("/stream-ping", dependencies=[Depends(is_authenticated)])
async def stream_ping(host: str, interval: int = 2):
    async def event_stream():
        while True:
            result = await is_host_online(host, retries=1, timeout=1, fallback_port=80)
            yield f"data: {json.dumps(result)}\n\n"
            await asyncio.sleep(interval)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/host/status", dependencies=[Depends(is_authenticated)])
async def host_online(
    host: str = Query(..., description="Hostname or IP address to check"),
    retries: int = 2,
    timeout: int = 1,
    port: int = 80
):
    result = await is_host_online(host, retries=retries, timeout=timeout, fallback_port=port)
    return result

@router.get("/speedtest")
async def speedtest_endpoint():
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, perform_speedtest)
    return results

def perform_speedtest():
    s = speedtest.Speedtest()
    s.get_best_server()
    s.download()
    s.upload()
    return s.results.dict()