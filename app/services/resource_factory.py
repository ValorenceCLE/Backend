"""
Resource factory for creating per-task resources.

This module provides factories for creating asyncio-aware resources
that are properly tied to the current event loop.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

class AsyncResourceFactory:
    """Factory for creating per-task async resources."""
    
    @staticmethod
    def create_lock():
        """Create a new asyncio lock tied to the current event loop."""
        return asyncio.Lock()
    
    @staticmethod
    def create_semaphore(value: int = 10):
        """Create a new asyncio semaphore tied to the current event loop."""
        return asyncio.Semaphore(value)
    
    @staticmethod
    async def create_influxdb_client():
        """Create a new InfluxDB client for the current task."""
        from app.core.env_settings import env
        from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
        
        client = InfluxDBClientAsync(
            url=env.INFLUXDB_URL,
            token=env.DOCKER_INFLUXDB_INIT_ADMIN_TOKEN,
            org=env.ORG
        )
        
        # Test connection
        try:
            if not await client.ping():
                logger.error("InfluxDB ping failed")
                return None
            return client
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}")
            return None
    
    @staticmethod
    def create_ina260_sensor(address: int):
        """Create a new INA260 sensor instance."""
        from app.services.smbus import INA260Sensor
        try:
            return INA260Sensor(address=address)
        except Exception as e:
            logger.error(f"Failed to create INA260 sensor at address {hex(address)}: {e}")
            return None
    
    @staticmethod
    def create_sht30_sensor(address: int = 0x45):
        """Create a new SHT30 sensor instance."""
        from app.services.smbus import SHT30Sensor
        try:
            return SHT30Sensor(address=address)
        except Exception as e:
            logger.error(f"Failed to create SHT30 sensor: {e}")
            return None