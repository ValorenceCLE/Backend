# app/api/configuration.py
# Add debug version with timeouts and better error handling
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from typing import Dict, Any, Optional
import asyncio
import traceback
import time

from app.core.services.config_manager import config_manager
from app.utils.dependencies import require_role, is_authenticated
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set to DEBUG for more verbose logging

router = APIRouter(prefix="/config", tags=["Admin API Configuration"])

# Add a health check endpoint to test basic router functionality
@router.get("/health", summary="Configuration API health check")
async def health_check():
    """Simple health check to verify the API is responsive."""
    logger.info("Config API health check called")
    return {"status": "healthy", "timestamp": time.time()}

@router.get("/", summary="Retrieve full configuration", dependencies=[Depends(is_authenticated)])
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
    
@router.get("/{config_section}", summary="Retrieve specific configuration section", dependencies=[Depends(is_authenticated)])
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
    
@router.post("/", summary="Update full custom configuration", dependencies=[Depends(require_role("admin"))])
async def update_custom_config(new_config: Dict[str, Any], background_tasks: BackgroundTasks):
    """Update the entire custom configuration in the background to avoid timeouts."""
    try:
        logger.debug("update_custom_config endpoint called")
        
        # Start a background task to update config
        background_tasks.add_task(_update_config_task, new_config)
        
        logger.info("Configuration update started in background")
        return {"message": "Configuration update started"}
    except Exception as e:
        logger.error(f"Error starting config update: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to start configuration update: {str(e)}")
    
@router.post("/{config_section}", summary="Update specific configuration section", dependencies=[Depends(require_role("admin"))])
async def update_config_section(config_section: str, new_config: Dict[str, Any], background_tasks: BackgroundTasks):
    """Update a specific section of the configuration in the background."""
    try:
        logger.debug(f"update_config_section endpoint called for section: {config_section}")
        
        # Start a background task to update config section
        background_tasks.add_task(_update_section_task, config_section, new_config)
        
        logger.info(f"Configuration section '{config_section}' update started in background")
        return {"message": f"Configuration section '{config_section}' update started"}
    except Exception as e:
        logger.error(f"Error starting config section update for '{config_section}': {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to start configuration section update: {str(e)}")

@router.post("/revert", summary="Revert to default configuration", dependencies=[Depends(require_role("admin"))])
async def revert_to_defaults(background_tasks: BackgroundTasks):
    """Revert to default configuration by removing custom configuration in the background."""
    try:
        logger.debug("revert_to_defaults endpoint called")
        
        # Start a background task to revert config
        background_tasks.add_task(_revert_config_task)
        
        logger.info("Configuration revert started in background")
        return {"message": "Configuration revert started"}
    except Exception as e:
        logger.error(f"Error starting config revert: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to start configuration revert: {str(e)}")

# Background tasks
async def _update_config_task(new_config: Dict[str, Any]):
    """Background task to update the entire configuration."""
    try:
        logger.info("Starting background config update")
        
        # Use a timeout to prevent hanging
        success = await asyncio.wait_for(
            config_manager.update_custom_config(new_config),
            timeout=30  # 30 second timeout
        )
        
        if success:
            logger.info("Background config update completed successfully")
        else:
            logger.error("Background config update failed")
    except asyncio.TimeoutError:
        logger.error("Background config update timed out after 30 seconds")
    except Exception as e:
        logger.error(f"Error in background config update: {str(e)}")
        logger.error(traceback.format_exc())

async def _update_section_task(section: str, new_config: Dict[str, Any]):
    """Background task to update a specific configuration section."""
    try:
        logger.info(f"Starting background config section update for '{section}'")
        
        # Use a timeout to prevent hanging
        success = await asyncio.wait_for(
            config_manager.update_custom_config_section(section, new_config),
            timeout=30  # 30 second timeout
        )
        
        if success:
            logger.info(f"Background config section update for '{section}' completed successfully")
        else:
            logger.error(f"Background config section update for '{section}' failed")
    except asyncio.TimeoutError:
        logger.error(f"Background config section update for '{section}' timed out after 30 seconds")
    except Exception as e:
        logger.error(f"Error in background config section update for '{section}': {str(e)}")
        logger.error(traceback.format_exc())

async def _revert_config_task():
    """Background task to revert configuration to defaults."""
    try:
        logger.info("Starting background config revert")
        
        # Use a timeout to prevent hanging
        success = await asyncio.wait_for(
            config_manager.revert_to_defaults(),
            timeout=30  # 30 second timeout
        )
        
        if success:
            logger.info("Background config revert completed successfully")
        else:
            logger.error("Background config revert failed")
    except asyncio.TimeoutError:
        logger.error("Background config revert timed out after 30 seconds")
    except Exception as e:
        logger.error(f"Error in background config revert: {str(e)}")
        logger.error(traceback.format_exc())