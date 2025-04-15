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
from app.services.influxdb_client import InfluxDBWriter
from celery_app import app

logger = logging.getLogger(__name__)

class SensorDataCollector:
    def __init__(self):
        self.influx_writer = InfluxDBWriter()
        self.semaphore = asyncio.Semaphore(10)  # Limit concurrent sensor reads
        
        # Sensor configurations
        self.ina260_sensors = [
            {"relay_id": "relay_1", "address": 0x44},
            {"relay_id": "relay_2", "address": 0x45},
            {"relay_id": "relay_3", "address": 0x46},
            {"relay_id": "relay_4", "address": 0x47},
            {"relay_id": "relay_5", "address": 0x48},
            {"relay_id": "relay_6", "address": 0x49},
            {"relay_id": "main", "address": 0x4B},
        ]
        
        # Sensor caches
        self._ina260_cache = {}
        self._sht30_cache = None
        
        # Sensor health tracking
        self._sensor_health = {}
        self._last_successful_reads = {}
    
    async def start(self):
        """Start the collector service"""
        await self.influx_writer.start()
    
    async def stop(self):
        """Stop the collector service"""
        await self.influx_writer.stop()
    
    async def collect_all_data(self):
        """Collect data from all sensors with improved concurrency control"""
        # Create tasks for all sensor readings
        tasks = []
        
        # Add relay sensor tasks
        for sensor_config in self.ina260_sensors:
            tasks.append(self._read_relay_sensor(
                sensor_config["relay_id"], 
                sensor_config["address"]
            ))
        
        # Add environmental sensor task
        tasks.append(self._read_environmental_sensor())
        
        # Run all tasks with concurrency control
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process the results
        success_count = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Sensor read error: {result}")
            elif result and result.get("success", False):
                success_count += 1
        
        return {
            "total": len(tasks),
            "success": success_count,
            "timestamp": datetime.now().isoformat()
        }
    
    async def _read_relay_sensor(self, relay_id, address):
        """Read a relay sensor with semaphore control and better error handling"""
        async with self.semaphore:
            sensor_key = f"ina260_{relay_id}"
            result = {
                "success": False,
                "sensor_id": sensor_key,
                "relay_id": relay_id
            }
            
            try:
                # Get or create sensor instance
                sensor = self._get_ina260_sensor(address)
                if not sensor:
                    result["error"] = "Failed to initialize sensor"
                    return result
                
                # Read sensor data with timeout
                data = await asyncio.wait_for(sensor.read_all(), timeout=2.0)
                if not data or None in data.values():
                    result["error"] = "Incomplete sensor data"
                    return result
                
                # Create timestamp for all operations
                timestamp = datetime.now(timezone.utc).isoformat()
                
                # Create InfluxDB point
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
                
                # Queue point for writing
                await self.influx_writer.write(point)
                
                # Update WebSocket data
                from app.api.websocket import update_sensor_data
                update_sensor_data(f"relay_{relay_id}", {
                    "timestamp": timestamp,
                    "relay_id": relay_id,
                    **data
                })
                
                # Track sensor health
                self._sensor_health[sensor_key] = True
                self._last_successful_reads[sensor_key] = datetime.now()
                
                # Trigger rule evaluation - using .delay() to make it async
                mapped_data = {
                    "volts": data["voltage"],
                    "amps": data["current"],
                    "watts": data["power"]
                }

                # Trigger rule evaluation with the correctly mapped data
                from app.core.tasks.rule_tasks import evaluate_rules
                evaluate_rules.delay(relay_id, mapped_data)
                
                # Update result
                result["success"] = True
                result["data"] = data
                result["timestamp"] = timestamp
                
                return result
                
            except asyncio.TimeoutError:
                result["error"] = "Sensor read timeout"
                self._sensor_health[sensor_key] = False
                return result
                
            except Exception as e:
                result["error"] = str(e)
                self._sensor_health[sensor_key] = False
                return result
    
    async def _read_environmental_sensor(self):
        """Read the environmental sensor with better error handling"""
        async with self.semaphore:
            sensor_key = "sht30"
            result = {
                "success": False,
                "sensor_id": sensor_key
            }
            
            try:
                # Get sensor instance
                sensor = self._get_sht30_sensor()
                if not sensor:
                    result["error"] = "Failed to initialize sensor"
                    return result
                
                # Reset sensor to ensure good readings
                await asyncio.wait_for(sensor.reset(), timeout=1.0)
                
                # Read sensor data with timeout
                data = await asyncio.wait_for(sensor.read_all(), timeout=2.0)
                if not data or None in data.values():
                    result["error"] = "Incomplete sensor data"
                    return result
                
                # Create timestamp
                timestamp = datetime.now(timezone.utc).isoformat()
                
                # Create InfluxDB point
                point = {
                    "measurement": "environmental",
                    "tags": {},
                    "fields": {
                        "temperature": data["temperature"],
                        "humidity": data["humidity"]
                    },
                    "time": timestamp
                }
                
                # Queue point for writing
                await self.influx_writer.write(point)
                
                # Update WebSocket data
                from app.api.websocket import update_sensor_data
                update_sensor_data("environmental", {
                    "timestamp": timestamp,
                    **data
                })
                
                # Track sensor health
                self._sensor_health[sensor_key] = True
                self._last_successful_reads[sensor_key] = datetime.now()

                mapped_data = {
                    "temperature": data["temperature"],
                    "humidity": data["humidity"]
                }
                
                # Trigger rule evaluation - using .delay() to make it async
                from app.core.tasks.rule_tasks import evaluate_rules
                evaluate_rules.delay("environmental", mapped_data)
                
                # Update result
                result["success"] = True
                result["data"] = data
                result["timestamp"] = timestamp
                
                return result
                
            except asyncio.TimeoutError:
                result["error"] = "Sensor read timeout"
                self._sensor_health[sensor_key] = False
                return result
                
            except Exception as e:
                result["error"] = str(e)
                self._sensor_health[sensor_key] = False
                return result
    
    def _get_ina260_sensor(self, address: int) -> Optional[INA260Sensor]:
        """Get or create an INA260 sensor instance with error handling"""
        address_str = hex(address)
        if address_str not in self._ina260_cache:
            try:
                self._ina260_cache[address_str] = INA260Sensor(address=address)
            except Exception as e:
                logger.error(f"Failed to initialize INA260 sensor at {address_str}: {e}")
                return None
                
        return self._ina260_cache[address_str]
    
    def _get_sht30_sensor(self) -> Optional[SHT30Sensor]:
        """Get or create an SHT30 sensor instance with error handling"""
        if self._sht30_cache is None:
            try:
                self._sht30_cache = SHT30Sensor(address=0x45)
            except Exception as e:
                logger.error(f"Failed to initialize SHT30 sensor: {e}")
                return None
                
        return self._sht30_cache
    
    def get_sensor_health(self):
        """Get health status of all sensors"""
        return {
            "sensors": self._sensor_health,
            "last_reads": {k: v.isoformat() for k, v in self._last_successful_reads.items()}
        }
    

# Initialize collector service as a singleton
_collector_service = None

def get_collector_service():
    """Get or create the collector service singleton"""
    global _collector_service
    if _collector_service is None:
        _collector_service = SensorDataCollector()
    return _collector_service

@app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3
)
def read_all_sensors(self):
    """
    Read all sensor data using the collector service.
    
    This task is scheduled to run periodically by Celery Beat.
    """
    logger.info("Reading all sensors")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # Get the collector service
        collector = get_collector_service()
        
        # Run the collection process
        result = loop.run_until_complete(collector.collect_all_data())
        
        if result["success"] > 0:
            logger.info(f"Successfully read {result['success']}/{result['total']} sensors")
        else:
            logger.warning(f"Failed to read any sensors ({result['total']} attempted)")
            
        return result
        
    except Exception as e:
        logger.error(f"Error reading sensors: {e}")
        self.retry(exc=e)
        return {"success": 0, "total": 0, "error": str(e)}
    finally:
        loop.close()