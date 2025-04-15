"""
Main entry point for the DPM FastAPI backend application.

This module initializes and starts the FastAPI application, sets up
routing for API endpoints, and configures middleware.
"""
from contextlib import asynccontextmanager
import json
import aiofiles
import uvicorn
import ssl
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from app.utils.config import settings
from app.services.influxdb_client import InfluxDBClientService
from app.api.auth import router as auth_router
from app.api.configuration import router as config_router
from app.api.relay import router as relay_router
from app.api.network import router as network_router
from app.api.device import router as device_router
from app.api.sensors import router as sensors_router
from app.api.timeseries import router as timeseries_router
import logging
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# SSL Configuration for production
ssl_context = None
cert_file = Path("/app/certs/deviceCert.crt")
key_file = Path("/app/certs/deviceCert.key")

if cert_file.exists() and key_file.exists():
    try:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        ssl_context.check_hostname = False
        logger.info(f"SSL configuration loaded from {cert_file} and {key_file}")
    except Exception as e:
        logger.error(f"Error loading SSL certificates: {e}")
        ssl_context = None
else:
    logger.warning(f"SSL certificates not found at {cert_file} and {key_file}, running without SSL")

async def wait_for_influxdb():
    """Wait for InfluxDB to be available"""
    from app.services.influxdb_client import InfluxDBClientService
    
    max_retries = 10
    retry_delay = 2  # seconds
    
    for i in range(max_retries):
        logger.info(f"Checking InfluxDB connection (attempt {i+1}/{max_retries})...")
        
        influxdb_client = InfluxDBClientService()
        if await influxdb_client.health_check():
            logger.info("InfluxDB is ready")
            return True
        
        await asyncio.sleep(retry_delay)
    
    logger.warning("Could not connect to InfluxDB after several attempts. Proceeding anyway.")
    return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load config at startup
    async with aiofiles.open("app/config/custom_config.json", "r") as file:
        app.state.config = json.loads(await file.read())
    
    # Wait for databases to be ready 
    await wait_for_influxdb()
    
    # Log application startup
    logger.info("Application started")
    
    yield
    
    # Save config at shutdown
    influxdb_client = InfluxDBClientService()
    await influxdb_client.close()
    async with aiofiles.open("app/config/custom_config.json", "w") as file:
        await file.write(json.dumps(app.state.config, indent=4))
    
    # Log application shutdown
    logger.info("Application shutting down")

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
    )

# Register API routers
app.include_router(auth_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(relay_router, prefix="/api")
app.include_router(network_router, prefix="/api")
app.include_router(device_router, prefix="/api")
app.include_router(sensors_router, prefix="/api")
app.include_router(timeseries_router, prefix="/api")

# WebSocket endpoints are registered directly in the router modules

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        ssl_keyfile=key_file if ssl_context else None,
        ssl_certfile=cert_file if ssl_context else None,
    )