import asyncio
import aioping
import logging
import time
from typing import List, Dict, Any, Tuple
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

SEM_LIMIT = 100
semaphore = asyncio.Semaphore(SEM_LIMIT)

# ------------------- Low-level Ping Functions -------------------

async def ping_host_icmp(host: str, timeout: int = 1) -> bool:
    try:
        async with semaphore:
            await aioping.ping(host, timeout=timeout)
            return True
    except TimeoutError:
        logging.debug(f"ICMP timeout for host {host}")
    except Exception as e:
        logging.debug(f"ICMP error for {host}: {e}")
    return False

async def check_tcp_port(host: str, port: int = 80, timeout: int = 1) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception as e:
        logging.debug(f"TCP port check failed for {host}:{port}: {e}")
    return False

# ------------------- Core Logic -------------------

async def is_host_online(
    host: str,
    retries: int = 2,
    timeout: int = 1,
    fallback_port: int = 80
) -> Dict[str, Any]:
    for attempt in range(1, retries + 2):
        start_time = time.perf_counter()
        icmp_success = await ping_host_icmp(host, timeout)
        icmp_latency = (time.perf_counter() - start_time) * 1000
        if icmp_success:
            return {
                "host": host,
                "online": True,
                "protocol": "ICMP",
                "latency_ms": round(icmp_latency, 2),
                "attempt": attempt
            }

        start_time = time.perf_counter()
        tcp_success = await check_tcp_port(host, port=fallback_port, timeout=timeout)
        tcp_latency = (time.perf_counter() - start_time) * 1000
        if tcp_success:
            return {
                "host": host,
                "online": True,
                "protocol": f"TCP:{fallback_port}",
                "latency_ms": round(tcp_latency, 2),
                "attempt": attempt
            }

    return {
        "host": host,
        "online": False,
        "attempts": retries + 1
    }

async def ping_hosts(
    hosts: List[str],
    retries: int = 2,
    timeout: int = 1,
    fallback_port: int = 80,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    start_time = datetime.now()
    tasks = [is_host_online(host, retries, timeout, fallback_port) for host in hosts]
    results = await asyncio.gather(*tasks)

    total = len(results)
    online_count = sum(1 for result in results if result["online"])
    offline_count = total - online_count
    duration = (datetime.now() - start_time).total_seconds()

    summary = {
        "total_hosts": total,
        "online": online_count,
        "offline": offline_count,
        "duration_sec": round(duration, 2)
    }

    return results, summary

# Optional indefinite loop function (can be used by background tasks)
async def ping_host_indefinitely(
    host: str,
    retries: int = 2,
    timeout: int = 1,
    fallback_port: int = 80,
    delay: int = 1
):
    try:
        while True:
            result = await is_host_online(host, retries, timeout, fallback_port)
            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        logging.info(f"[Cancelled] Pinging for {host} stopped.")
