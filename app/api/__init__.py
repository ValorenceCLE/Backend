from fastapi import APIRouter
from app.api.auth import router as auth_router
from app.api.configuration import router as config_router
from app.api.device import router as device_router
from app.api.network import router as network_router
from app.api.relay import router as relay_router
from app.api.sensors import router as sensors_router
from app.api.timeseries import router as timeseries_router

api_router = APIRouter()

# Include all the routers
api_router.include_router(auth_router)
api_router.include_router(config_router)
api_router.include_router(device_router)
api_router.include_router(network_router)
api_router.include_router(relay_router)
api_router.include_router(sensors_router)
api_router.include_router(timeseries_router)