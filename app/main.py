# app/main.py
# Update the main application entry point
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from app.middleware import setup_middleware
from app.core.services.config_manager import config_manager
from app.core.env_settings import env
from app.api import api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)



# Create FastAPI application

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifecycle events."""
    try:
        logger.info("Starting application initialization")
        
        # Initialize the configuration manager first
        logger.info("Initializing configuration manager")
        success = await config_manager.initialize()
        
        if success:
            logger.info("Configuration manager initialized successfully")
        else:
            logger.error("Failed to initialize configuration manager")
    except Exception as e:
        logger.error(f"Error during application startup: {e}")
    
    yield  # This is where the application runs
    
    # Cleanup code (if any) would go here
    logger.info("Shutting down application")

# Use the lifespan for app lifecycle management
app = FastAPI(
    title=env.APP_NAME, 
    description="FastAPI Backend Valorence Control System",
    lifespan=lifespan
)
setup_middleware(app)
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
app.include_router(api_router, prefix="/api")

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