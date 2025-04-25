# app/api/configuration.py
from fastapi import APIRouter, HTTPException, Depends, status
from typing import Dict, Any, Optional

from app.core.services.config_manager import config_manager
from app.utils.dependencies import require_role, is_authenticated
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["Admin API Configuration"])

@router.get("/", summary="Retrieve full configuration", dependencies=[Depends(is_authenticated)])
async def get_full_config():
    """Get the full effective configuration."""
    return config_manager.get_full_config()
    
@router.get("/{config_section}", summary="Retrieve specific configuration section", dependencies=[Depends(is_authenticated)])
async def get_config_section(config_section: str):
    """Get a specific section of the configuration."""
    section = config_manager.get_section(config_section)
    if not section:
        raise HTTPException(status_code=404, detail=f"Configuration section '{config_section}' not found")
    return section
    
@router.post("/", summary="Update full custom configuration", dependencies=[Depends(require_role("admin"))])
async def update_custom_config(new_config: Dict[str, Any]):
    """Update the entire custom configuration."""
    success = await config_manager.update_custom_config(new_config)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid configuration")
    return {"message": "Configuration updated successfully"}
    
@router.post("/{config_section}", summary="Update specific configuration section", dependencies=[Depends(require_role("admin"))])
async def update_config_section(config_section: str, new_config: Dict[str, Any]):
    """Update a specific section of the configuration."""
    success = await config_manager.update_custom_config_section(config_section, new_config)
    if not success:
        raise HTTPException(status_code=400, detail=f"Invalid configuration for section '{config_section}'")
    return {"message": f"Configuration section '{config_section}' updated successfully"}

@router.post("/revert", summary="Revert to default configuration", dependencies=[Depends(require_role("admin"))])
async def revert_to_defaults():
    """Revert to default configuration by removing custom configuration."""
    success = await config_manager.revert_to_defaults()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to revert to default configuration")
    return {"message": "Reverted to default configuration successfully"}
