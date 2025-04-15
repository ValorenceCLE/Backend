"""
System monitoring tasks.

This module defines Celery tasks for monitoring system performance,
hardware status, and network connectivity.
"""
import asyncio
import logging
import psutil
import time
from datetime import datetime, timezone
from typing import Dict, Any
from celery_app import app
from app.services.influxdb_client import InfluxDBClientService

logger = logging.getLogger(__name__)

@app.task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3
)
def monitor_system():
    """
    Monitor system performance and store metrics in InfluxDB.
    
    This task is scheduled to run periodically by Celery Beat.
    """
    logger.debug("Running system monitoring")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_collect_system_metrics())
        return True
    except Exception as e:
        logger.error(f"Error monitoring system: {e}")
        return False
    finally:
        loop.close()

async def _collect_system_metrics():
    """Collect and store system performance metrics"""
    try:
        # Collect CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Collect memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Collect disk usage
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        
        # Collect network stats
        net_io = psutil.net_io_counters()
        
        # Store in InfluxDB
        influx = InfluxDBClientService()
        await influx.connect()
        
        try:
            # Create data point for InfluxDB
            timestamp = datetime.now(timezone.utc).isoformat()
            point = {
                "measurement": "system_metrics",
                "tags": {},
                "fields": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory_percent,
                    "disk_percent": disk_percent,
                    "bytes_sent": net_io.bytes_sent,
                    "bytes_recv": net_io.bytes_recv
                },
                "time": timestamp
            }
            
            # Write to InfluxDB
            await influx.write_point(point)
            logger.debug(f"Stored system metrics: CPU {cpu_percent}%, Memory {memory_percent}%, Disk {disk_percent}%")
            
            # Update WebSocket data
            from app.api.websocket import update_sensor_data
            update_sensor_data("system", {
                "timestamp": timestamp,
                "cpu": cpu_percent,
                "memory": memory_percent,
                "disk": disk_percent
            })
            
        finally:
            # Ensure connection is closed
            await influx.close()
            
    except Exception as e:
        logger.error(f"Error collecting system metrics: {e}")

@app.task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3
)
def check_network_connectivity():
    """
    Check network connectivity to important hosts.
    
    This task is scheduled to run periodically by Celery Beat.
    """
    logger.debug("Checking network connectivity")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_check_connectivity())
        return True
    except Exception as e:
        logger.error(f"Error checking network connectivity: {e}")
        return False
    finally:
        loop.close()

async def _check_connectivity():
    """Check connectivity to important hosts"""
    # This implementation will depend on your specific networking needs
    # For demonstration purposes, we'll just log a message
    logger.info("Network connectivity check would be implemented here")