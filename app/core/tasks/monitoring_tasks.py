"""
app/core/tasks/monitoring_tasks.py
System monitoring tasks.

This module defines Celery tasks for monitoring system performance,
hardware status, and network connectivity.
"""
import asyncio
import logging
import psutil
from datetime import datetime, timezone
from celery_app import app
from app.services.influxdb_client import InfluxDBWriter

logger = logging.getLogger(__name__)

@app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3
)
def monitor_system(self):
    """
    Monitor system performance and store metrics in InfluxDB.
    
    This task is scheduled to run periodically by Celery Beat.
    """
    logger.debug("Running system monitoring")
    
    try:
        # Collect metrics synchronously to avoid event loop issues
        # Collect CPU usage (non-blocking)
        cpu_percent = psutil.cpu_percent(interval=None)  # Use shorter interval
        
        # Collect memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Collect disk usage
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        
        # Create data point to store in InfluxDB
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
        
        # Store directly in InfluxDB
        influx_writer = InfluxDBWriter()
        influx_writer.write(point)
        
        # Update WebSocket data (non-blocking)
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
            
        logger.info(f"System metrics collected: CPU {cpu_percent}%, Memory {memory_percent}%, Disk {disk_percent}%")
        return {
            "cpu": cpu_percent,
            "memory": memory_percent,
            "disk": disk_percent
        }
    except Exception as e:
        logger.error(f"Error monitoring system: {e}", exc_info=True)
        self.retry(exc=e)
        return None
@app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3
)
def check_network_connectivity(self):
    """
    Check network connectivity to important hosts.
    
    This task is scheduled to run periodically by Celery Beat.
    """
    logger.debug("Checking network connectivity")
    
    try:
        # Use system ping command to avoid event loop issues
        import subprocess
        hosts = ["8.8.8.8", "1.1.1.1", "google.com"]
        results = {}
        
        for host in hosts:
            try:
                # Use system ping command with timeout
                result = subprocess.run(
                    ["ping", "-c", "1", "-W", "2", host],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=3
                )
                success = result.returncode == 0
                results[host] = success
                logger.debug(f"Ping to {host}: {'Success' if success else 'Failed'}")
            except Exception as e:
                logger.error(f"Error pinging {host}: {e}")
                results[host] = False
        
        # Record network connectivity in InfluxDB
        point = {
            "measurement": "network_connectivity",
            "tags": {},
            "fields": {
                host.replace(".", "_"): int(status) for host, status in results.items()
            },
            "time": datetime.now(timezone.utc).isoformat()
        }
        influx_writer = InfluxDBWriter()
        influx_writer.write(point)
        
        # Calculate overall status
        online = sum(1 for status in results.values() if status)
        total = len(results)
        
        logger.info(f"Network connectivity: {online}/{total} hosts reachable")
        return {
            "hosts": results,
            "online": online,
            "total": total
        }
    except Exception as e:
        logger.error(f"Error checking network connectivity: {e}", exc_info=True)
        self.retry(exc=e)
        return None

@app.task(bind=True, max_retries=3)
def write_influx_point(self, point):
    """
    Write a data point to InfluxDB.
    
    This is a helper task to avoid blocking other tasks when writing to InfluxDB.
    """
    try:
        from app.services.influxdb_client import InfluxDBWriter
        influx = InfluxDBWriter()
        
        # Use synchronous approach to avoid event loop issues
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(influx.write(point))
            logger.debug(f"Successfully wrote point to InfluxDB: {point['measurement']}")
            return True
        except Exception as e:
            logger.error(f"Error writing to InfluxDB: {e}")
            self.retry(exc=e)
            return False
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error creating InfluxDB writer: {e}")
        self.retry(exc=e)
        return False