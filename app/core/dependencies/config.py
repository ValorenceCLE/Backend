# app/core/dependencies/config.py
from fastapi import Depends
from typing import Dict, Any, List, Optional

from app.core.services.config_manager import config_manager

async def get_config():
    """
    Dependency provider for the full effective configuration.
    
    Use this when you need access to the entire configuration.
    """
    return config_manager.get_full_config()

async def get_config_section(section: str):
    """
    Factory for creating dependency providers for specific configuration sections.
    
    Example:
        get_network_config = Depends(get_config_section("network"))
    """
    def _get_section():
        return config_manager.get_section(section)
    return _get_section

async def get_hardware_config():
    """Dependency provider for hardware configuration."""
    return config_manager.get_hardware_config()

# Common section dependencies
get_general_config = Depends(get_config_section("general"))
get_network_config = Depends(get_config_section("network"))
get_datetime_config = Depends(get_config_section("date_time"))
get_relays_config = Depends(get_config_section("relays"))
get_tasks_config = Depends(get_config_section("tasks"))