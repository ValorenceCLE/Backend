"""
InfluxDB client with proper async handling.

This module provides a non-singleton InfluxDB client that doesn't share
state between workers and properly handles event loop isolation.
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class InfluxDBClient:
    """Non-singleton InfluxDB client that doesn't share state between workers."""
    
    def __init__(self):
        """Initialize with settings but don't create any asyncio objects."""
        from app.core.env_settings import env
        self.url = env.INFLUXDB_URL
        self.token = env.DOCKER_INFLUXDB_INIT_ADMIN_TOKEN
        self.org = env.ORG
        self.bucket = env.BUCKET
    
    async def write_points(self, points: List[Dict[str, Any]]) -> bool:
        """
        Write points directly without buffering.
        
        Args:
            points: List of data points to write
            
        Returns:
            bool: True if write was successful, False otherwise
        """
        if not points:
            return True
            
        client = None
        try:
            # Create new client for this operation
            from app.services.resource_factory import AsyncResourceFactory
            client = await AsyncResourceFactory.create_influxdb_client()
            
            if not client:
                logger.error("Failed to create InfluxDB client")
                return False
            
            # Write points
            write_api = client.write_api()
            await write_api.write(
                bucket=self.bucket,
                org=self.org,
                record=points
            )
            logger.debug(f"Successfully wrote {len(points)} points to InfluxDB")
            return True
        except Exception as e:
            logger.error(f"Error writing to InfluxDB: {e}")
            return False
        finally:
            # Always close client
            if client:
                try:
                    await client.close()
                except Exception as e:
                    logger.warning(f"Error closing InfluxDB client: {e}")
    
    async def query(self, query_text: str) -> Optional[List[Any]]:
        """
        Execute a Flux query against InfluxDB.
        
        Args:
            query_text: The Flux query string
            
        Returns:
            Optional list of query results or None on error
        """
        client = None
        try:
            # Create new client for this operation
            from app.services.resource_factory import AsyncResourceFactory
            client = await AsyncResourceFactory.create_influxdb_client()
            
            if not client:
                logger.error("Failed to create InfluxDB client for query")
                return None
            
            # Execute query
            query_api = client.query_api()
            results = await query_api.query(query_text)
            return results
        except Exception as e:
            logger.error(f"Error executing InfluxDB query: {e}")
            return None
        finally:
            # Always close client
            if client:
                try:
                    await client.close()
                except Exception as e:
                    logger.warning(f"Error closing InfluxDB client: {e}")