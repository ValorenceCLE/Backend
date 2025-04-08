import logging
from typing import List, Optional
from datetime import datetime
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.flux_table import FluxTable
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class InfluxDBClientService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(InfluxDBClientService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        from app.utils.config import settings
        self.url = settings.INFLUXDB_URL
        self.token = settings.DOCKER_INFLUXDB_INIT_ADMIN_TOKEN
        self.org = settings.ORG
        self.bucket = settings.BUCKET
        self.client = None
        self._initialized = True
    
    async def connect(self):
        if self.client is None:
            try:
                self.client = InfluxDBClientAsync(
                    url=self.url,
                    token=self.token,
                    org=self.org
                )
                logger.info("Connected to InfluxDB")
            except Exception as e:
                logger.error(f"Failed to connect to InfluxDB: {e}")
                raise e
    
    @asynccontextmanager
    async def get_client(self):
        """Context manager to ensure client is properly closed after use"""
        try:
            await self.connect()
            yield self.client
        finally:
            # We don't close the client here as it's a singleton
            # Just yield it for the operation
            pass
    
    async def query(self, query: str) -> List[FluxTable]:
        """Execute a Flux query against InfluxDB with proper connection handling"""
        try:
            await self.connect()
            query_api = self.client.query_api()
            logger.debug(f"Executing query: {query}")
            result = await query_api.query(query=query, org=self.org)  # Ensure org is passed
            return result
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise e
        
    async def close(self):
        """Explicitly close the client connection"""
        if self.client:
            await self.client.close()
            self.client = None
            logger.info("Closed InfluxDB connection")