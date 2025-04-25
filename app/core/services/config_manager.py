# app/core/services/config_manager.py
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Callable, Awaitable
from pydantic import ValidationError
import copy
import aiofiles
import json

from app.core.env_settings import env
from app.core.models.config_models import ApplicationConfig  # You'll need to create this

logger = logging.getLogger(__name__)

ConfigChangeListener = Callable[[Dict[str, Any]], Awaitable[None]]

class ConfigurationManager:
    """
    Asynchronous configuration manager with hot reloading.
    """
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ConfigurationManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        # Paths from environment
        self.default_config_path = env.default_config_path
        self.custom_config_path = env.custom_config_path
        
        # Configuration state
        self._default_config: Dict[str, Any] = {}
        self._custom_config: Dict[str, Any] = {}
        self._hardware_config: Dict[str, Any] = {
            "ina260_sensors": env.INA260_SENSORS,
            "gpio_chip": env.GPIO_CHIP,
            "relays": env.HARDWARE_CONFIG
        }
        self._effective_config: Dict[str, Any] = {}
        
        # Concurrency control
        self._lock = asyncio.Lock()
        
        # Event system
        self._change_listeners: List[ConfigChangeListener] = []
        self._section_listeners: Dict[str, List[ConfigChangeListener]] = {}
        
        # Cache for frequent lookups
        self._relay_cache: Dict[str, Dict[str, Any]] = {}
        self._task_cache: Dict[str, Dict[str, Any]] = {}
        
        self._initialized = True
    
    async def initialize(self) -> bool:
        """Initialize the configuration manager."""
        logger.info("Initializing configuration manager")
        return await self.load_all_configs()
    
    async def load_all_configs(self) -> bool:
        """Load all configuration files and generate effective configuration."""
        async with self._lock:
            # Load configurations
            default_loaded = await self._load_default_config()
            custom_loaded = await self._load_custom_config()
            
            if not default_loaded:
                logger.error("Failed to load default configuration")
                return False
            
            # Generate effective configuration
            self._generate_effective_config()
            
            # Build caches
            self._build_caches()
            
            # Notify listeners
            await self._notify_listeners()
            
            return True
    
    async def _load_default_config(self) -> bool:
        """Load the default configuration."""
        try:
            if self.default_config_path.exists():
                async with aiofiles.open(self.default_config_path, "r") as f:
                    content = await f.read()
                    self._default_config = json.loads(content)
                logger.info(f"Loaded default configuration from {self.default_config_path}")
                return True
            else:
                logger.warning(f"Default config file not found at {self.default_config_path}")
                return False
        except Exception as e:
            logger.error(f"Error loading default config: {e}")
            return False
    
    async def _load_custom_config(self) -> bool:
        """Load the custom configuration if it exists."""
        try:
            if self.custom_config_path.exists():
                async with aiofiles.open(self.custom_config_path, "r") as f:
                    content = await f.read()
                    self._custom_config = json.loads(content)
                logger.info(f"Loaded custom configuration from {self.custom_config_path}")
                return True
            else:
                self._custom_config = {}
                logger.info("No custom configuration found")
                return True
        except Exception as e:
            logger.error(f"Error loading custom config: {e}")
            self._custom_config = {}
            return True  # Non-critical error
    
    def _generate_effective_config(self) -> None:
        """Generate the effective configuration by merging default and custom."""
        # Start with a deep copy of the default
        self._effective_config = copy.deepcopy(self._default_config)
        
        # Apply custom configuration on top
        if self._custom_config:
            self._deep_merge(self._effective_config, self._custom_config)
        
        logger.debug("Generated effective configuration")
    
    def _deep_merge(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """
        Deep merge source into target.
        Lists of objects with IDs are merged by ID matching.
        """
        for key, value in source.items():
            if key in target:
                if isinstance(value, dict) and isinstance(target[key], dict):
                    # Both are dictionaries - recurse
                    self._deep_merge(target[key], value)
                elif isinstance(value, list) and isinstance(target[key], list):
                    # Handle special cases for lists
                    if key in {"relays", "tasks"} and all(isinstance(i, dict) for i in target[key] + value if i):
                        # Merge list items by ID
                        self._merge_list_by_id(target[key], value)
                    else:
                        # Replace the entire list
                        target[key] = copy.deepcopy(value)
                else:
                    # Simple value - replace
                    target[key] = copy.deepcopy(value)
            else:
                # Key doesn't exist in target - add it
                target[key] = copy.deepcopy(value)
    
    def _merge_list_by_id(self, target_list: List[Dict[str, Any]], source_list: List[Dict[str, Any]]) -> None:
        """Merge two lists of dictionaries by 'id' field."""
        # Create a dictionary mapping IDs to items
        target_dict = {item.get("id"): item for item in target_list if isinstance(item, dict) and "id" in item}
        
        # Process source items
        for source_item in source_list:
            if isinstance(source_item, dict) and "id" in source_item:
                item_id = source_item["id"]
                if item_id in target_dict:
                    # Update existing item
                    if isinstance(source_item, dict) and isinstance(target_dict[item_id], dict):
                        self._deep_merge(target_dict[item_id], source_item)
                else:
                    # Add new item
                    target_list.append(copy.deepcopy(source_item))
    
    def _build_caches(self) -> None:
        """Build caches for frequent lookups."""
        # Cache relay configurations by ID
        self._relay_cache = {}
        for relay in self._effective_config.get("relays", []):
            if isinstance(relay, dict) and "id" in relay:
                self._relay_cache[relay["id"]] = relay
        
        # Cache task configurations by ID
        self._task_cache = {}
        for task in self._effective_config.get("tasks", []):
            if isinstance(task, dict) and "id" in task:
                self._task_cache[task["id"]] = task
                
        logger.debug("Built configuration caches")
    
    async def update_custom_config(self, new_config: Dict[str, Any]) -> bool:
        """Update the entire custom configuration."""
        async with self._lock:
            # Store the new configuration
            self._custom_config = copy.deepcopy(new_config)
            
            # Generate effective configuration
            self._generate_effective_config()
            
            # Save to disk
            success = await self._save_custom_config()
            
            # Rebuild caches
            self._build_caches()
            
            # Notify listeners
            await self._notify_listeners()
            
            return success
    
    async def _save_custom_config(self) -> bool:
        """Save custom configuration to disk."""
        try:
            async with aiofiles.open(self.custom_config_path, "w") as f:
                await f.write(json.dumps(self._custom_config, indent=4))
            logger.info(f"Saved custom configuration to {self.custom_config_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving custom configuration: {e}")
            return False
    
    async def update_custom_config_section(self, section: str, new_section: Dict[str, Any]) -> bool:
        """Update a specific section of the custom configuration."""
        async with self._lock:
            # Create a new custom config with the updated section
            updated_config = copy.deepcopy(self._custom_config)
            
            # If this is our first custom config, start with default
            if not updated_config:
                updated_config = copy.deepcopy(self._default_config)
            
            # Update the section
            updated_config[section] = copy.deepcopy(new_section)
            
            # Update the entire config
            return await self.update_custom_config(updated_config)
    
    async def revert_to_defaults(self) -> bool:
        """Revert to default configuration by removing custom configuration."""
        async with self._lock:
            # Clear custom config
            self._custom_config = {}
            
            # Set effective config to default
            self._effective_config = copy.deepcopy(self._default_config)
            
            # Delete the custom config file if it exists
            try:
                if self.custom_config_path.exists():
                    self.custom_config_path.unlink()
                    logger.info(f"Deleted custom configuration file: {self.custom_config_path}")
            except Exception as e:
                logger.error(f"Error deleting custom configuration file: {e}")
            
            # Rebuild caches
            self._build_caches()
            
            # Notify listeners
            await self._notify_listeners()
            
            return True
    
    async def register_listener(self, listener: ConfigChangeListener, sections: Optional[List[str]] = None) -> None:
        """
        Register a listener for configuration changes.
        
        Args:
            listener: Async function to call when config changes
            sections: Optional list of section names to listen for, or None for all changes
        """
        if sections:
            # Register for specific sections
            for section in sections:
                if section not in self._section_listeners:
                    self._section_listeners[section] = []
                self._section_listeners[section].append(listener)
        else:
            # Register for all changes
            self._change_listeners.append(listener)
    
    async def unregister_listener(self, listener: ConfigChangeListener) -> None:
        """Unregister a listener from all sections."""
        # Remove from global listeners
        if listener in self._change_listeners:
            self._change_listeners.remove(listener)
        
        # Remove from section listeners
        for section_listeners in self._section_listeners.values():
            if listener in section_listeners:
                section_listeners.remove(listener)
    
    async def _notify_listeners(self) -> None:
        """Notify all registered listeners of configuration changes."""
        # Determine which sections changed
        changed_sections: Set[str] = set()
        
        # For simplicity, assume all sections might have changed
        # In a more optimized version, you could track actual changes
        changed_sections = set(self._effective_config.keys())
        
        # Notify global listeners
        tasks = []
        for listener in self._change_listeners:
            tasks.append(listener(self._effective_config))
        
        # Notify section-specific listeners
        for section in changed_sections:
            if section in self._section_listeners:
                for listener in self._section_listeners[section]:
                    tasks.append(listener(self._effective_config))
        
        # Wait for all notifications to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    # Access methods
    
    def get_full_config(self) -> Dict[str, Any]:
        """Get the complete effective configuration."""
        return self._effective_config
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get a specific section of the configuration."""
        return self._effective_config.get(section, {})
    
    def get_hardware_config(self) -> Dict[str, Any]:
        """Get the hardware configuration."""
        return self._hardware_config
    
    def get_relay_config(self, relay_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific relay by ID."""
        return self._relay_cache.get(relay_id)
    
    def get_task_config(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific task by ID."""
        return self._task_cache.get(task_id)
    
    def get_sensor_config(self, sensor_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific sensor by ID."""
        # Find sensor configuration by relay ID or sensor ID
        for sensor in env.INA260_SENSORS:
            if sensor.get("relay_id") == sensor_id or sensor.get("id") == sensor_id:
                return sensor
                
        return None
    
    def get_value(self, path: str, default: Any = None) -> Any:
        """
        Get a configuration value by dot-notation path.
        
        Example: get_value("general.system_name")
        """
        parts = path.split('.')
        current = self._effective_config
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        
        return current

# Create singleton instance
config_manager = ConfigurationManager()