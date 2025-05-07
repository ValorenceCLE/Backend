# app/services/influxdb_client.py
import logging
import asyncio
from typing import List
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.flux_table import FluxTable
import time

logging.getLogger('aiohttp').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class InfluxDBConnectionManager:
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(InfluxDBConnectionManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        from app.core.env_settings import env as settings
        self.url = settings.INFLUXDB_URL
        self.token = settings.DOCKER_INFLUXDB_INIT_ADMIN_TOKEN
        self.org = settings.ORG
        self.bucket = settings.BUCKET
        self.client = None
        self._initialized = True
        
        # Circuit breaker state
        self.failure_count = 0
        self.last_failure_time = time.time()
        self.circuit_open = False
        self.reset_timeout = 60  # seconds
        self.failure_threshold = 5
        
    async def get_client(self):
        """Get a new InfluxDB client with circuit breaker pattern"""
        async with self._lock:
            # Check if circuit breaker is open
            if self.circuit_open:
                current_time = time.time()
                if current_time - self.last_failure_time > self.reset_timeout:
                    # Reset circuit breaker after timeout
                    logger.info("Circuit breaker reset - attempting to reconnect to InfluxDB")
                    self.circuit_open = False
                    self.failure_count = 0
                else:
                    # Circuit still open - fail fast
                    logger.debug("Circuit breaker open - skipping InfluxDB connection")
                    return None
            
            # Always create a new client - don't cache
            try:
                client = InfluxDBClientAsync(
                    url=self.url,
                    token=self.token,
                    org=self.org
                )
                logger.debug("Created new InfluxDB client")
                
                # Test connection
                if not await client.ping():
                    await self._handle_connection_failure("Ping failed")
                    # Close the client if ping fails
                    await client.close()
                    return None
                    
                # Connection successful - reset failure count
                self.failure_count = 0
                return client
            except Exception as e:
                await self._handle_connection_failure(str(e))
                return None
    
    async def _handle_connection_failure(self, reason):
        """Handle connection failure with circuit breaker logic"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        # Close existing client if any
        if self.client:
            try:
                await self.client.close()
            except Exception:
                pass
            self.client = None
            
        # Check if we should open circuit breaker
        if self.failure_count >= self.failure_threshold:
            if not self.circuit_open:
                logger.warning(f"Opening circuit breaker after {self.failure_count} failures")
                self.circuit_open = True
        
        logger.error(f"InfluxDB connection failure ({reason}). Failure count: {self.failure_count}")

    async def close(self):
        """Close the client connection"""
        async with self._lock:
            if self.client:
                try:
                    await self.client.close()
                    self.client = None
                    logger.debug("Closed InfluxDB client")
                except Exception as e:
                    logger.warning(f"Error closing InfluxDB client: {e}")
                    self.client = None


class InfluxDBWriter:
    def __init__(self):
        self.connection_manager = InfluxDBConnectionManager()
        self.batch_size = 20
        self.flush_interval = 5  # seconds
        self.points_buffer = []
        self.buffer_lock = asyncio.Lock()
        self._shutdown = False
        self._flush_task = None
    
    async def start(self):
        """Start the background flush task"""
        self._shutdown = False
        self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.debug("Started InfluxDB writer background task")
    
    async def stop(self):
        """Stop the writer and flush remaining points"""
        self._shutdown = True
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            
        # Final flush
        await self.flush()
        logger.debug("Stopped InfluxDB writer")
    
    async def write(self, point):
        """Queue a point for writing"""
        async with self.buffer_lock:
            self.points_buffer.append(point)
            
            # Auto-flush if we hit the batch size
            if len(self.points_buffer) >= self.batch_size:
                await self._flush_internal()
    
    async def flush(self):
        """Manually flush the buffer"""
        async with self.buffer_lock:
            await self._flush_internal()
    
    async def _flush_internal(self):
        """Internal method to flush points - must be called with lock held"""
        if not self.points_buffer:
            return
            
        points_to_write = self.points_buffer.copy()
        self.points_buffer = []
        
        # Get client from connection manager
        client = await self.connection_manager.get_client()
        if not client:
            logger.error(f"Failed to get InfluxDB client, discarding {len(points_to_write)} points")
            return
            
        try:
            # Write the batch
            write_api = client.write_api()
            await write_api.write(
                bucket=self.connection_manager.bucket,
                org=self.connection_manager.org,
                record=points_to_write
            )
            logger.debug(f"Successfully wrote {len(points_to_write)} points to InfluxDB")
        except Exception as e:
            logger.error(f"Error writing batch to InfluxDB: {e}")
        finally:
            # Ensure client is properly closed to clean up aiohttp resources
            try:
                await client.close()
            except Exception as e:
                logger.warning(f"Error closing InfluxDB client: {e}")
            
    async def _periodic_flush(self):
        """Background task to periodically flush the buffer"""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic flush: {e}")


class InfluxDBReader:
    def __init__(self):
        self.connection_manager = InfluxDBConnectionManager()
        self.bucket = self.connection_manager.bucket
        self.org = self.connection_manager.org

    
    async def query(self, query: str) -> List[FluxTable]:
        """Execute a Flux query and return the results"""
        client = await self.connection_manager.get_client()
        if not client:
            logger.error("Failed to get InfluxDB client for query")
            return None
            
        try:
            results = await client.query_api().query(query)
            return results
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return None
        finally:
            await self.connection_manager.close()