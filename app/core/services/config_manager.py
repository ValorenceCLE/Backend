# app/core/services/config_manager.py
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Callable, Awaitable
from pydantic import ValidationError
import copy
import aiofiles
import json
import time

from app.core.env_settings import env
from app.core.models.config_models import ApplicationConfig  # You'll need to create this

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set to DEBUG for more verbose logging

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
        self._initialization_lock = asyncio.Lock()  # New lock just for initialization
        self._is_initialized = False  # Track whether initialize() has completed successfully
        self._init_error = None  # Track initialization errors
        
        # Event system
        self._change_listeners: List[ConfigChangeListener] = []
        self._section_listeners: Dict[str, List[ConfigChangeListener]] = {}
        
        # Cache for frequent lookups
        self._relay_cache: Dict[str, Dict[str, Any]] = {}
        self._task_cache: Dict[str, Dict[str, Any]] = {}
        
        self._initialized = True
    
    async def initialize(self) -> bool:
        """Initialize the configuration manager."""
        # Use a separate lock for initialization to avoid deadlock
        async with self._initialization_lock:
            if self._is_initialized:
                logger.info("Configuration manager already initialized")
                return True
                
            logger.info("Initializing configuration manager")
            try:
                start_time = time.time()
                result = await self.load_all_configs()
                self._is_initialized = result
                logger.info(f"Configuration manager initialized in {time.time() - start_time:.2f} seconds, success={result}")
                if not result:
                    self._init_error = "Failed to load default configuration"
                return result
            except Exception as e:
                logger.error(f"Error during configuration manager initialization: {e}")
                self._init_error = str(e)
                self._is_initialized = False
                return False
    
    async def load_all_configs(self) -> bool:
        """Load all configuration files and generate effective configuration."""
        logger.debug("Starting to load all configs")
        try:
            # Use a timeout to prevent deadlocks on the lock
            lock_acquired = False
            try:
                # Try to acquire the lock with a timeout
                lock_acquired = await asyncio.wait_for(self._lock.acquire(), timeout=5.0)
                
                # Load configurations
                start_time = time.time()
                logger.debug("Loading default config")
                default_loaded = await self._load_default_config()
                if not default_loaded:
                    logger.error("Failed to load default configuration")
                    return False
                
                logger.debug("Loading custom config")
                custom_loaded = await self._load_custom_config()
                
                # Generate effective configuration
                logger.debug("Generating effective config")
                self._generate_effective_config()
                
                # Build caches
                logger.debug("Building caches")
                self._build_caches()
                
                # Release lock before notifying listeners to avoid potential deadlocks
                # if listeners try to access configuration
                if lock_acquired:
                    self._lock.release()
                    lock_acquired = False
                
                # Notify listeners
                logger.debug("Notifying listeners")
                await self._notify_listeners()
                
                logger.info(f"All configs loaded in {time.time() - start_time:.2f} seconds")
                return True
            finally:
                # Make sure we always release the lock
                if lock_acquired and self._lock.locked():
                    self._lock.release()
        except Exception as e:
            logger.error(f"Error in load_all_configs: {e}")
            return False
    
    async def _load_default_config(self) -> bool:
        """Load the default configuration."""
        try:
            if self.default_config_path.exists():
                start_time = time.time()
                async with aiofiles.open(self.default_config_path, "r") as f:
                    content = await f.read()
                    try:
                        self._default_config = json.loads(content)
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON in default config: {e}")
                        return False
                logger.info(f"Loaded default configuration from {self.default_config_path} in {time.time() - start_time:.2f} seconds")
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
                start_time = time.time()
                async with aiofiles.open(self.custom_config_path, "r") as f:
                    content = await f.read()
                    try:
                        self._custom_config = json.loads(content)
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON in custom config: {e}")
                        # Continue with empty custom config rather than failing
                        self._custom_config = {}
                logger.info(f"Loaded custom configuration from {self.custom_config_path} in {time.time() - start_time:.2f} seconds")
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
        logger.debug("update_custom_config called")
        try:
            # Try to acquire the lock with a timeout
            logger.debug("Acquiring lock for update_custom_config")
            await asyncio.wait_for(self._lock.acquire(), timeout=5.0)
            
            try:
                # Store the new configuration
                self._custom_config = copy.deepcopy(new_config)
                
                # Generate effective configuration
                self._generate_effective_config()
                
                # Save to disk
                logger.debug("Saving custom config to disk")
                success = await self._save_custom_config()
                
                # Rebuild caches
                self._build_caches()
                
                # Release lock before notifying listeners
                self._lock.release()
                
                # Notify listeners
                logger.debug("Notifying listeners about config update")
                await self._notify_listeners()
                
                return success
            finally:
                # Make sure we always release the lock
                if self._lock.locked():
                    self._lock.release()
                    logger.debug("Lock released in update_custom_config")
        except asyncio.TimeoutError:
            logger.error("Timeout acquiring lock in update_custom_config")
            return False
        except Exception as e:
            logger.error(f"Error in update_custom_config: {e}")
            return False
    
    async def _save_custom_config(self) -> bool:
        """Save custom configuration to disk."""
        try:
            start_time = time.time()
            async with aiofiles.open(self.custom_config_path, "w") as f:
                json_string = json.dumps(self._custom_config, indent=4)
                await f.write(json_string)
            logger.info(f"Saved custom configuration to {self.custom_config_path} in {time.time() - start_time:.2f} seconds")
            return True
        except Exception as e:
            logger.error(f"Error saving custom configuration: {e}")
            return False
    
    async def update_custom_config_section(self, section: str, new_section: Dict[str, Any]) -> bool:
        """Update a specific section of the custom configuration."""
        logger.debug(f"update_custom_config_section called for section: {section}")
        try:
            # Try to acquire the lock with a timeout
            logger.debug(f"Acquiring lock for update_custom_config_section: {section}")
            await asyncio.wait_for(self._lock.acquire(), timeout=5.0)
            
            try:
                # Create a new custom config with the updated section
                updated_config = copy.deepcopy(self._custom_config)
                
                # If this is our first custom config, start with default
                if not updated_config:
                    updated_config = copy.deepcopy(self._default_config)
                
                # Update the section
                updated_config[section] = copy.deepcopy(new_section)
                
                # Release lock before calling update_custom_config which also uses the lock
                self._lock.release()
                
                # Update the entire config
                logger.debug(f"Calling update_custom_config from update_custom_config_section: {section}")
                return await self.update_custom_config(updated_config)
            finally:
                # Make sure we always release the lock
                if self._lock.locked():
                    self._lock.release()
                    logger.debug(f"Lock released in update_custom_config_section: {section}")
        except asyncio.TimeoutError:
            logger.error(f"Timeout acquiring lock in update_custom_config_section: {section}")
            return False
        except Exception as e:
            logger.error(f"Error in update_custom_config_section for section {section}: {e}")
            return False
    
    async def revert_to_defaults(self) -> bool:
        """Revert to default configuration by removing custom configuration."""
        logger.debug("revert_to_defaults called")
        try:
            # Try to acquire the lock with a timeout
            logger.debug("Acquiring lock for revert_to_defaults")
            await asyncio.wait_for(self._lock.acquire(), timeout=5.0)
            
            try:
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
                
                # Release lock before notifying listeners
                self._lock.release()
                
                # Notify listeners
                logger.debug("Notifying listeners about config revert")
                await self._notify_listeners()
                
                return True
            finally:
                # Make sure we always release the lock
                if self._lock.locked():
                    self._lock.release()
                    logger.debug("Lock released in revert_to_defaults")
        except asyncio.TimeoutError:
            logger.error("Timeout acquiring lock in revert_to_defaults")
            return False
        except Exception as e:
            logger.error(f"Error in revert_to_defaults: {e}")
            return False
    
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
        """Notify all registered listeners of configuration changes with timeout protection."""
        logger.debug("Starting _notify_listeners")
        
        # Determine which sections changed
        changed_sections: Set[str] = set()
        
        # For simplicity, assume all sections might have changed
        # In a more optimized version, you could track actual changes
        changed_sections = set(self._effective_config.keys())
        
        # Notify global listeners
        tasks = []
        for listener in self._change_listeners:
            tasks.append(self._notify_single_listener(listener, self._effective_config))
        
        # Notify section-specific listeners
        for section in changed_sections:
            if section in self._section_listeners:
                for listener in self._section_listeners[section]:
                    tasks.append(self._notify_single_listener(listener, self._effective_config))
        
        # Wait for all notifications to complete with timeout
        if tasks:
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Log any errors in notification
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"Listener #{i} failed: {result}")
                        
                logger.debug(f"Notified {len(tasks)} listeners")
            except Exception as e:
                logger.error(f"Error in _notify_listeners gather: {e}")
                
    async def _notify_single_listener(self, listener: ConfigChangeListener, config: Dict[str, Any]) -> bool:
        """Notify a single listener with timeout protection."""
        try:
            # Apply a timeout to each listener to prevent one from blocking others
            await asyncio.wait_for(listener(config), timeout=5.0)
            return True
        except asyncio.TimeoutError:
            logger.error(f"Listener {listener.__name__ if hasattr(listener, '__name__') else 'unknown'} timed out")
            return False
        except Exception as e:
            logger.error(f"Error in listener {listener.__name__ if hasattr(listener, '__name__') else 'unknown'}: {e}")
            return False
    
    # Access methods
    
    def get_full_config(self) -> Dict[str, Any]:
        """Get the complete effective configuration."""
        # Check if initialization has completed
        if not self._is_initialized:
            logger.warning("Configuration manager has not completed initialization")
            if self._init_error:
                logger.error(f"Initialization error: {self._init_error}")
            return {"error": "Configuration manager not fully initialized"}
        
        # Return a copy to prevent external modifications
        return copy.deepcopy(self._effective_config)
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get a specific section of the configuration."""
        # Check if initialization has completed
        if not self._is_initialized:
            logger.warning(f"Configuration manager has not completed initialization when getting section {section}")
            return {}
            
        # Get section with safe fallback
        result = self._effective_config.get(section, {})
        
        # Return a copy to prevent external modifications
        return copy.deepcopy(result)
    
    def get_hardware_config(self) -> Dict[str, Any]:
        """Get the hardware configuration."""
        return copy.deepcopy(self._hardware_config)
    
    def get_relay_config(self, relay_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific relay by ID."""
        result = self._relay_cache.get(relay_id)
        return copy.deepcopy(result) if result else None
    
    def get_task_config(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific task by ID."""
        result = self._task_cache.get(task_id)
        return copy.deepcopy(result) if result else None
    
    def get_sensor_config(self, sensor_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific sensor by ID."""
        # Find sensor configuration by relay ID or sensor ID
        for sensor in env.INA260_SENSORS:
            if sensor.get("relay_id") == sensor_id or sensor.get("id") == sensor_id:
                return copy.deepcopy(sensor)
                
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
        
        # For mutable types, return a copy to prevent external modifications
        if isinstance(current, (dict, list)):
            return copy.deepcopy(current)
        return current
        
# Create singleton instance
config_manager = ConfigurationManager()