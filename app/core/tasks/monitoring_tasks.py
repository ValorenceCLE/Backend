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
from app.services.influxdb_client import InfluxDBWriter

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

# app/core/tasks/monitoring_tasks.py
# In the _collect_system_metrics function

async def _collect_system_metrics():
    """Collect and store system performance metrics"""
    try:
        # Collect CPU usage (non-blocking)
        cpu_percent = psutil.cpu_percent(interval=0.5)
        
        # Collect memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Collect disk usage
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        
        # Store in InfluxDB
        try:
            # Create data point
            timestamp = datetime.now(timezone.utc).isoformat()
            point = {
                "measurement": "system_metrics",
                "tags": {},
                "fields": {
                    "cpu_percent": float(cpu_percent),
                    "memory_percent": float(memory_percent),
                    "disk_percent": float(disk_percent)
                },
                "time": timestamp
            }
            
            # Use a fresh client
            influx = InfluxDBWriter()
            success = await influx.write(point)
            
            if success:
                logger.debug(f"Stored system metrics: CPU {cpu_percent}%, Memory {memory_percent}%, Disk {disk_percent}%")
            
            # Update WebSocket data regardless of storage success
            try:
                from app.api.websocket import update_sensor_data
                update_sensor_data("system", {
                    "timestamp": timestamp,
                    "cpu": cpu_percent,
                    "memory": memory_percent,
                    "disk": disk_percent
                })
            except Exception as e:
                logger.error(f"Error updating WebSocket data: {e}")
            
        except Exception as e:
            logger.error(f"Error storing system metrics: {e}")
            
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