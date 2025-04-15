"""
Sensor data collection tasks.

This module defines Celery tasks for collecting data from various sensors,
processing the data, and storing it in InfluxDB.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from app.services.smbus import INA260Sensor, SHT30Sensor
from app.services.influxdb_client import InfluxDBClientService
from celery_app import app

logger = logging.getLogger(__name__)

# Global sensor caches
_ina260_sensors = {}
_sht30_sensor = None

def _get_ina260_sensor(address: int) -> INA260Sensor:
    """Get or create an INA260 sensor instance"""
    global _ina260_sensors
    if address not in _ina260_sensors:
        _ina260_sensors[address] = INA260Sensor(address=address)
    return _ina260_sensors[address]

def _get_sht30_sensor() -> Optional[SHT30Sensor]:
    """Get or create an SHT30 sensor instance"""
    global _sht30_sensor
    if _sht30_sensor is None:
        try:
            _sht30_sensor = SHT30Sensor(address=0x45)
        except Exception as e:
            logger.error(f"Failed to initialize SHT30 sensor: {e}")
            return None
    return _sht30_sensor

@app.task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3
)
def read_all_sensors():
    """
    Read all sensor data, store in InfluxDB, and trigger rules evaluation.
    
    This task is scheduled to run periodically by Celery Beat.
    """
    logger.debug("Reading all sensors")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_collect_all_sensor_data())
        return True
    except Exception as e:
        logger.error(f"Error reading sensors: {e}")
        return False
    finally:
        loop.close()

async def _collect_all_sensor_data():
    """Asynchronously collect data from all sensors"""
    # INA260 relay sensors configuration
    ina260_configs = [
        {"relay_id": "relay_1", "address": 0x44},
        {"relay_id": "relay_2", "address": 0x45},
        {"relay_id": "relay_3", "address": 0x46},
        {"relay_id": "relay_4", "address": 0x47},
        {"relay_id": "relay_5", "address": 0x48},
        {"relay_id": "relay_6", "address": 0x49},
        {"relay_id": "main", "address": 0x4B},
    ]
    
    # Collect data from relay sensors
    relay_tasks = []
    for config in ina260_configs:
        relay_tasks.append(_collect_relay_data(config["relay_id"], config["address"]))
    
    # Collect environmental data
    env_task = _collect_environmental_data()
    
    # Run all tasks concurrently
    await asyncio.gather(*relay_tasks, env_task, return_exceptions=True)

async def _collect_relay_data(relay_id: str, address: int):
    """Collect data from a relay's INA260 sensor"""
    try:
        # Get sensor instance
        sensor = _get_ina260_sensor(address)
        if not sensor:
            logger.warning(f"No sensor available for {relay_id}")
            return
        
        # Read sensor data
        data = await sensor.read_all()
        if not data or None in data.values():
            logger.warning(f"Incomplete sensor data for {relay_id}")
            return
        
        # Store in InfluxDB
        influx = InfluxDBClientService()
        await influx.connect()
        
        try:
            # Create data point for InfluxDB
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
            
            # Write to InfluxDB
            await influx.write_point(point)
            logger.debug(f"Stored data for {relay_id}: {data}")
            
            # Update WebSocket data
            from app.api.websocket import update_sensor_data
            update_sensor_data(f"relay_{relay_id}", {
                "timestamp": timestamp,
                "relay_id": relay_id,
                **data
            })
            
            # Trigger rule evaluation as a separate task
            from app.core.tasks.rule_tasks import evaluate_rules
            evaluate_rules.delay(relay_id, data)
            
        finally:
            # Ensure connection is closed
            await influx.close()
            
    except Exception as e:
        logger.error(f"Error collecting data for {relay_id}: {e}")

async def _collect_environmental_data():
    """Collect data from environmental sensor"""
    try:
        # Get sensor instance
        sensor = _get_sht30_sensor()
        if not sensor:
            logger.warning("No environmental sensor available")
            return
        
        # Reset sensor to ensure good readings
        await sensor.reset()
        
        # Read sensor data
        data = await sensor.read_all()
        if not data or None in data.values():
            logger.warning("Incomplete environmental sensor data")
            return
        
        # Store in InfluxDB
        influx = InfluxDBClientService()
        await influx.connect()
        
        try:
            # Create data point for InfluxDB
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
            
            # Write to InfluxDB
            await influx.write_point(point)
            logger.debug(f"Stored environmental data: {data}")
            
            # Update WebSocket data
            from app.api.websocket import update_sensor_data
            update_sensor_data("environmental", {
                "timestamp": timestamp,
                **data
            })
            
            # Trigger rule evaluation as a separate task
            from app.core.tasks.rule_tasks import evaluate_rules
            evaluate_rules.delay("environmental", data)
            
        finally:
            # Ensure connection is closed
            await influx.close()
            
    except Exception as e:
        logger.error(f"Error collecting environmental data: {e}")