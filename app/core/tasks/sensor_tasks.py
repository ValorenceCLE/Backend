"""
Sensor data collection and processing tasks.

This module defines Celery tasks for reading sensor data, storing it in InfluxDB,
updating WebSockets, and triggering rule evaluation.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any
from celery_app import app
from app.core.tasks.common import run_task_with_new_loop, TaskMetrics

logger = logging.getLogger(__name__)

@app.task
@run_task_with_new_loop
async def read_all_sensors() -> Dict[str, Any]:
    """
    Read all sensor data and process it.
    
    This task reads data from all configured sensors, stores it in InfluxDB,
    updates WebSockets, and triggers rule evaluation.
    
    Returns:
        Dict with collection results and statistics
    """
    with TaskMetrics("read_all_sensors") as metrics:
        # Task context metrics
        results = {
            "total": 0,
            "success": 0,
            "errors": 0
        }
        
        try:
            # Get sensor configurations
            from app.core.env_settings import env
            sensor_configs = env.INA260_SENSORS
            
            # Create task-specific resources
            from app.services.influxdb_client import InfluxDBClient
            influxdb_client = InfluxDBClient()
            points_to_write = []
            
            # Prepare tasks for concurrent execution
            tasks = []
            for config in sensor_configs:
                tasks.append(_read_sensor(config["relay_id"], config["address"]))
            
            # Also read environmental sensor
            tasks.append(_read_environmental_sensor())
            
            # Execute all sensor reads concurrently
            results["total"] = len(tasks)
            sensor_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in sensor_results:
                if isinstance(result, Exception):
                    results["errors"] += 1
                    metrics.increment("errors")
                    logger.error(f"Sensor read error: {result}")
                    continue
                    
                if not result or not result.get("success"):
                    results["errors"] += 1
                    metrics.increment("errors")
                    continue
                    
                # Task succeeded
                results["success"] += 1
                metrics.increment("success")
                
                # Add point to batch if available
                if "point" in result:
                    points_to_write.append(result["point"])
                    
                # Trigger rule evaluation if data available
                if "data" in result and "source" in result:
                    from app.core.tasks.rule_tasks import evaluate_rules
                    evaluate_rules.delay(result["source"], result["data"])
                    
                # Update WebSocket if applicable
                if "websocket_data" in result and "websocket_source" in result:
                    from app.api.websocket import update_sensor_data
                    update_sensor_data(result["websocket_source"], result["websocket_data"])
            
            # Write all points in a single batch
            if points_to_write:
                await influxdb_client.write_points(points_to_write)
            
            # Calculate duration and add timestamp
            results["timestamp"] = datetime.now().isoformat()
            
            return results
        except Exception as e:
            logger.error(f"Error in read_all_sensors task: {e}")
            metrics.increment("errors")
            results["error"] = str(e)
            return results

async def _read_sensor(relay_id: str, address: int) -> Dict[str, Any]:
    """
    Read a single sensor without shared state.
    
    Creates a new sensor instance each time to avoid event loop issues.
    
    Args:
        relay_id: Identifier for the relay
        address: I2C address for the sensor
        
    Returns:
        Dict with sensor reading results
    """
    try:
        # Create a new sensor instance every time
        from app.services.resource_factory import AsyncResourceFactory
        sensor = AsyncResourceFactory.create_ina260_sensor(address)
        
        if not sensor:
            return {"success": False, "error": f"Failed to create sensor for relay {relay_id}"}
        
        # Read data with timeout
        try:
            data = await asyncio.wait_for(sensor.read_all(), timeout=2.0)
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Timeout reading sensor for relay {relay_id}"}
            
        if not data or None in data.values():
            return {"success": False, "error": "Incomplete sensor data"}
        
        # Create point for InfluxDB
        timestamp = datetime.now(timezone.utc).isoformat()
        point = {
            "measurement": "relay_power",
            "tags": {"relay_id": relay_id},
            "fields": {
                "voltage": data["voltage"],
                "current": data["current"],
                "power": data["power"]
            },
            "time": timestamp
        }
        
        # Map data for rules
        mapped_data = {
            "volts": data["voltage"],
            "amps": data["current"],
            "watts": data["power"]
        }
        
        # WebSocket data
        websocket_data = {
            "timestamp": timestamp,
            "relay_id": relay_id,
            **data
        }
        
        # Return all required data
        return {
            "success": True,
            "source": relay_id,
            "data": mapped_data,
            "point": point,
            "websocket_source": f"relay_{relay_id}",
            "websocket_data": websocket_data
        }
    except Exception as e:
        logger.error(f"Error reading sensor {relay_id}: {e}")
        return {"success": False, "error": str(e)}

async def _read_environmental_sensor() -> Dict[str, Any]:
    """
    Read data from the environmental sensor.
    
    Returns:
        Dict with environmental sensor reading results
    """
    try:
        # Create a new sensor instance every time
        from app.services.resource_factory import AsyncResourceFactory
        sensor = AsyncResourceFactory.create_sht30_sensor()
        
        if not sensor:
            return {"success": False, "error": "Failed to create SHT30 sensor"}
        
        # Reset sensor to ensure good readings
        try:
            await asyncio.wait_for(sensor.reset(), timeout=1.0)
        except asyncio.TimeoutError:
            return {"success": False, "error": "Timeout resetting SHT30 sensor"}
        
        # Read data with timeout
        try:
            data = await asyncio.wait_for(sensor.read_all(), timeout=2.0)
        except asyncio.TimeoutError:
            return {"success": False, "error": "Timeout reading SHT30 sensor"}
            
        if not data or None in data.values():
            return {"success": False, "error": "Incomplete environmental sensor data"}
        
        # Create point for InfluxDB
        timestamp = datetime.now(timezone.utc).isoformat()
        point = {
            "measurement": "environmental",
            "tags": {},
            "fields": {
                "temperature": data["temperature"],
                "humidity": data["humidity"]
            },
            "time": timestamp
        }
        
        # Data for rules is the same as sensor data
        mapped_data = {
            "temperature": data["temperature"],
            "humidity": data["humidity"]
        }
        
        # WebSocket data
        websocket_data = {
            "timestamp": timestamp,
            **data
        }
        
        # Return all required data
        return {
            "success": True,
            "source": "environmental",
            "data": mapped_data,
            "point": point,
            "websocket_source": "environmental",
            "websocket_data": websocket_data
        }
    except Exception as e:
        logger.error(f"Error reading environmental sensor: {e}")
        return {"success": False, "error": str(e)}
