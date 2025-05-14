# app/api/configuration.py
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Dict, Any, Optional
import asyncio
import traceback
from app.core.services.config_manager import config_manager
from app.utils.dependencies import require_role, is_authenticated, is_admin
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set to DEBUG for more verbose logging

router = APIRouter(prefix="/config", tags=["Admin API Configuration"])

@router.get("/", summary="Retrieve full configuration")
async def get_full_config():
    """Get the full effective configuration with timeout protection."""
    try:
        logger.debug("get_full_config endpoint called")
        
        # Get config with a timeout to prevent hanging
        config = config_manager.get_full_config()
        if config is None or not isinstance(config, dict):
            logger.error(f"Invalid configuration returned: {type(config)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve valid configuration")
            
        logger.info("Full configuration retrieved successfully")
        return config
    except Exception as e:
        logger.error(f"Error in get_full_config: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to retrieve configuration: {str(e)}")

@router.post("/", summary="Update full custom configuration")
async def update_custom_config(new_config: Dict[str, Any]):
    """Update the entire custom configuration and always return the updated configuration."""
    try:
        logger.debug("update_custom_config endpoint called")
        
        # Update the configuration and wait for completion
        try:
            success = await config_manager.update_custom_config(new_config)
            
            if not success:
                logger.error("Failed to update configuration")
                raise HTTPException(status_code=500, detail="Failed to update configuration")
            
            # Get the updated configuration
            updated_config = config_manager.get_full_config()
            
            # Return both success message and updated configuration
            response = {
                "message": "Configuration updated successfully",
                "config": updated_config
            }
            
            logger.info("Configuration updated and returned successfully")
            return response
            
        except Exception as e:
            logger.error(f"Error during configuration update: {str(e)}")
            raise HTTPException(status_code=500, 
                               detail=f"Failed to update configuration: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error in update_custom_config: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")
    
@router.get("/{config_section}", summary="Retrieve specific configuration section")
async def get_config_section(config_section: str):
    """Get a specific section of the configuration with timeout protection."""
    try:
        logger.debug(f"get_config_section endpoint called for section: {config_section}")
        
        # Get section with a timeout to prevent hanging
        section = config_manager.get_section(config_section)
        
        if section is None:
            logger.warning(f"Configuration section '{config_section}' not found")
            raise HTTPException(status_code=404, detail=f"Configuration section '{config_section}' not found")
            
        logger.info(f"Configuration section '{config_section}' retrieved successfully")
        return section
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Error in get_config_section for '{config_section}': {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to retrieve configuration section: {str(e)}")
    
@router.post("/{config_section}", summary="Update specific configuration section")
async def update_config_section(config_section: str, new_config: Dict[str, Any]):
    """Update a specific section of the configuration and always return the updated section."""
    try:
        logger.debug(f"update_config_section endpoint called for section: {config_section}")
        
        # Update the section and wait for completion
        try:
            success = await config_manager.update_custom_config_section(config_section, new_config)
            
            if not success:
                logger.error(f"Failed to update configuration section: {config_section}")
                raise HTTPException(status_code=500, 
                                   detail=f"Failed to update configuration section: {config_section}")
            
            # Get the updated section
            updated_section = config_manager.get_section(config_section)
            
            # Return both success message and updated section
            response = {
                "message": f"Configuration section '{config_section}' updated successfully",
                "section": updated_section
            }
            
            logger.info(f"Configuration section '{config_section}' updated and returned successfully")
            return response
            
        except Exception as e:
            logger.error(f"Error updating configuration section '{config_section}': {str(e)}")
            raise HTTPException(status_code=500, 
                               detail=f"Failed to update configuration section: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error in update_config_section for '{config_section}': {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to update configuration section: {str(e)}")

@router.post("/revert", summary="Revert to default configuration")
async def revert_to_defaults():
    """Revert to default configuration and return the default configuration."""
    try:
        logger.debug("revert_to_defaults endpoint called")
        
        # Revert to defaults and wait for completion
        try:
            success = await config_manager.revert_to_defaults()
            
            if not success:
                logger.error("Failed to revert to default configuration")
                raise HTTPException(status_code=500, detail="Failed to revert to default configuration")
            
            # Get the default configuration (now the current configuration)
            default_config = config_manager.get_full_config()
            
            # Return both success message and default configuration
            response = {
                "message": "Configuration reverted to defaults successfully",
                "config": default_config
            }
            
            logger.info("Configuration reverted to defaults and returned successfully")
            return response
            
        except Exception as e:
            logger.error(f"Error reverting to default configuration: {str(e)}")
            raise HTTPException(status_code=500, 
                               detail=f"Failed to revert to default configuration: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error in revert_to_defaults: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to revert to default configuration: {str(e)}")