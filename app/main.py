# app/main.py
# Update the main application entry point
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.core.services.config_manager import config_manager
from app.core.env_settings import env
from app.api.auth import router as auth_router
from app.api.configuration import router as config_router
from app.api.relay import router as relay_router
from app.api.network import router as network_router
from app.api.device import router as device_router
from app.api.sensors import router as sensors_router
from app.api.timeseries import router as timeseries_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle events."""
    # Initialize configuration manager
    config_success = await config_manager.initialize()
    if not config_success:
        logger.error("Failed to initialize configuration. Application may not function correctly.")
    
    # Store config in app state for backward compatibility during refactoring
    app.state.config = config_manager.get_full_config()
    
    # Register a change listener to keep app.state.config updated
    async def update_app_state_config(new_config):
        app.state.config = new_config
    await config_manager.register_listener(update_app_state_config)
    
    # Log application startup
    logger.info(f"Application {env.APP_NAME} started")
    
    yield
    
    # Log application shutdown
    logger.info("Application shutting down")

# Create FastAPI application
app = FastAPI(
    title=env.APP_NAME, 
    description="FastAPI Backend Valorence Control System",
    lifespan=lifespan
)

# Add middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handler
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error"},
    )

# Register API routers
app.include_router(auth_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(relay_router, prefix="/api")
app.include_router(network_router, prefix="/api")
app.include_router(device_router, prefix="/api")
app.include_router(sensors_router, prefix="/api")
app.include_router(timeseries_router, prefix="/api")

# If running as a script
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        ssl_keyfile=env.SSL_KEY_FILE,
        ssl_certfile=env.SSL_CERT_FILE,
    )