"""
app/core/tasks/monitoring_tasks.py
System monitoring tasks.

This module defines Celery tasks for monitoring system performance,
hardware status, and network connectivity.
"""
import asyncio
import logging
import psutil
import time
import subprocess
from datetime import datetime, timezone
from celery_app import app
from app.services.influxdb_client import InfluxDBWriter

logger = logging.getLogger(__name__)

# Store previous network counters to calculate rates
_last_net_io = None
_last_net_time = None

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
    global _last_net_io, _last_net_time
    
    logger.debug("Running system monitoring")
    
    try:
        # Collect metrics synchronously to avoid event loop issues
        # Collect CPU usage (non-blocking)
        cpu_percent = psutil.cpu_percent(interval=None)
        
        # Collect memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Collect disk usage
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        disk_io = psutil.disk_io_counters()

        # Collect network usage
        current_time = time.time()
        net_io = psutil.net_io_counters()
        
        # Network metrics dictionary
        network_metrics = {
            "error_in": net_io.errin,
            "error_out": net_io.errout,
            "drop_in": net_io.dropin,
            "drop_out": net_io.dropout,
        }
        
        # Calculate network rates if we have previous measurements
        if _last_net_io and _last_net_time:
            time_diff = current_time - _last_net_time
            
            # Calculate bytes per second rates
            bytes_sent_rate = (net_io.bytes_sent - _last_net_io.bytes_sent) / time_diff
            bytes_recv_rate = (net_io.bytes_recv - _last_net_io.bytes_recv) / time_diff
            
            # Calculate packets per second rates
            packets_sent_rate = (net_io.packets_sent - _last_net_io.packets_sent) / time_diff
            packets_recv_rate = (net_io.packets_recv - _last_net_io.packets_recv) / time_diff
            
            # Calculate error rates
            errors_in_rate = (net_io.errin - _last_net_io.errin) / time_diff
            errors_out_rate = (net_io.errout - _last_net_io.errout) / time_diff
            
            # Calculate drop rates
            drops_in_rate = (net_io.dropin - _last_net_io.dropin) / time_diff
            drops_out_rate = (net_io.dropout - _last_net_io.dropout) / time_diff
            
            # Add rates to network metrics
            network_metrics.update({
                "bytes_sent_rate": float(bytes_sent_rate),
                "bytes_recv_rate": float(bytes_recv_rate),
                "packets_sent_rate": float(packets_sent_rate),
                "packets_recv_rate": float(packets_recv_rate),
                "errors_in_rate": float(errors_in_rate),
                "errors_out_rate": float(errors_out_rate),
                "drops_in_rate": float(drops_in_rate),
                "drops_out_rate": float(drops_out_rate),
            })
        
        # Store current values for next calculation
        _last_net_io = net_io
        _last_net_time = current_time
        
        # Get network connection count
        connections = len(psutil.net_connections())
        network_metrics["connection_count"] = connections
        
        # Measure network latency (ping to Google DNS)
        try:
            ping_result = subprocess.run(
                ["ping", "-c", "1", "8.8.8.8"], 
                capture_output=True, 
                text=True, 
                timeout=2
            )
            if ping_result.returncode == 0:
                # Extract ping time from output
                output = ping_result.stdout
                time_parts = output.split("time=")
                if len(time_parts) > 1:
                    latency_str = time_parts[1].split()[0]
                    latency = float(latency_str)
                    network_metrics["latency_ms"] = latency
        except (subprocess.SubprocessError, ValueError, IndexError) as e:
            logger.warning(f"Failed to measure network latency: {e}")
        
        # Create data point to store in InfluxDB
        timestamp = datetime.now(timezone.utc).isoformat()
        point = {
            "measurement": "system_metrics",
            "tags": {},
            "fields": {
                "cpu_percent": float(cpu_percent),
                "memory_percent": float(memory_percent),
                "disk_percent": float(disk_percent),
                **network_metrics  # Include all network metrics
            },
            "time": timestamp
        }
        
        # Store directly in InfluxDB
        influx_writer = InfluxDBWriter()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(influx_writer.start())
        try:
            loop.run_until_complete(influx_writer.write(point))
        except Exception as e:
            logger.error(f"Error writing to InfluxDB: {e}")
        finally:
            loop.run_until_complete(influx_writer.stop())
            loop.close()
        
        # Update WebSocket data (non-blocking)
        try:
            from app.api.websocket import update_sensor_data
            update_sensor_data("system", {
                "timestamp": timestamp,
                "cpu": cpu_percent,
                "memory": memory_percent,
                "disk": disk_percent,
                "network": network_metrics
            })
        except Exception as e:
            logger.error(f"Error updating WebSocket data: {e}")
            
        logger.info(f"System metrics collected: CPU {cpu_percent}%, Memory {memory_percent}%, Disk {disk_percent}%")
        return {
            "cpu": cpu_percent,
            "memory": memory_percent,
            "disk": disk_percent,
            "network": network_metrics
        }
    except Exception as e:
        logger.error(f"Error monitoring system: {e}", exc_info=True)
        self.retry(exc=e)
        return None
