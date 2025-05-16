# app/api/configuration.py
from fastapi import APIRouter, HTTPException, Depends, status
from typing import Dict, Any
from app.utils.dependencies import is_authenticated
from app.core.config import config_manager # New config_manager to replace the old one
import logging


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/config", tags=["Admin API Configuration"], dependencies=[Depends(is_authenticated)])

@router.get("/")
async def get_full_config():
    """Get the full configuration."""
    return config_manager.get_config().model_dump()

@router.post("/")
async def update_config(config_data: Dict[str, Any]):
    """Update the entire configuration."""
    try:
        updated = config_manager.update_config(config_data)
        return {
            "message": "Configuration updated successfully",
            "config": updated.model_dump()
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update configuration: {str(e)}"
        )

@router.get("/{section}")
async def get_config_section(section: str):
    """Get a specific section of the configuration."""
    config = config_manager.get_config().model_dump()
    if section not in config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration section '{section}' not found"
        )
    return config[section]

@router.post("/{section}")
async def update_config_section(section: str, section_data: Dict[str, Any]):
    """Update a specific section of the configuration."""
    try:
        updated = config_manager.update_section(section, section_data)
        return {
            "message": f"Configuration section '{section}' updated successfully",
            "section": updated.model_dump()[section]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update configuration section: {str(e)}"
        )

@router.post("/default/revert")
async def revert_to_defaults():
    """Revert to default configuration."""
    try:
        logger.info("Attempting to revert configuration to defaults")
        updated = config_manager.reset_to_defaults()
        logger.info("Successfully reverted configuration to defaults")
        return {
            "message": "Configuration reverted to defaults successfully",
            "config": updated.model_dump()
        }
    except Exception as e:
        logger.error(f"Failed to revert configuration to defaults: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revert to defaults: {str(e)}"
        )