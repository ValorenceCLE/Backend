from fastapi import Path
from typing import Dict, Any, List
from pathlib import Path as Pathlib
from app.core.config.models import AppConfig, RelayConfig, Task

async def get_config() -> AppConfig:
    """
    Dependency to get the application configuration.
    
    Returns:
        AppConfig: The application configuration.
    """
    return config_manager.get_config()

async def get_config_section(section: str = Path(...)) -> Dict[str, Any]:
    """Dependency to get a specific configuration section."""
    config = config_manager.get_config().model_dump()
    if section not in config:
        return {}
    return config[section]

async def get_relay_configs() -> List[RelayConfig]:
    """Dependency to get relay configurations."""
    return config_manager.get_config().relays

async def get_task_configs() -> List[Task]:
    """Dependency to get task configurations."""
    return config_manager.get_config().tasks

def create_config_manager():
    """Create the configuration manager singleton."""
    #from app.core.env_settings import env
    from app.core.config.manager import SimpleConfigManager
    from app.core.config.models import AppConfig
    from app.core.env_settings import env

    return SimpleConfigManager(
        config_class=AppConfig,
        config_path=Pathlib(env.CUSTOM_CONFIG_FILE),
        default_config_path=Pathlib(env.CONFIG_FILE)
    )

config_manager = create_config_manager()
