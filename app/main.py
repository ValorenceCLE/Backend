from contextlib import asynccontextmanager
import json
import aiofiles
import uvicorn
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load config at startup
    async with aiofiles.open("app/config/custom_config.json", "r") as file:
        app.state.config = json.loads(await file.read())
    yield
    # Save config at shutdown
    influxdb_client = InfluxDBClientService()
    await influxdb_client.close()
    async with aiofiles.open("app/config/custom_config.json", "w") as file:
        await file.write(json.dumps(app.state.config, indent=4))


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS - Updated for WebSocket support
app.add_middleware(
    CORSMiddleware,
    # Allow all origins in development; in production you would limit this
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

# Routers
app.include_router(auth_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(relay_router, prefix="/api")
app.include_router(network_router, prefix="/api")
app.include_router(device_router, prefix="/api")
app.include_router(sensors_router, prefix="/api")
app.include_router(timeseries_router, prefix="/api")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )