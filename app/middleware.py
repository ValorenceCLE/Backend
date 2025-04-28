# app/middleware.py
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.services.config_manager import config_manager

class ConfigMiddleware(BaseHTTPMiddleware):
    """
    Middleware to ensure the effective configuration is available in request.app.state
    """
    async def dispatch(self, request, call_next):
        # Add config to app state if not already present
        if not hasattr(request.app.state, "config"):
            request.app.state.config = config_manager.get_full_config()
        
        response = await call_next(request)
        return response

def setup_middleware(app: FastAPI):
    """Add all middleware to the application"""
    app.add_middleware(ConfigMiddleware)