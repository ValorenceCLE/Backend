import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, TypeVar, Type, Generic

from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

logger = logging.getLogger(__name__)

class SimpleConfigManager(Generic[T]):
    """
    Simple configuration manager that loads and saves configuration.
    Uses Pydantic models for validation and type safety.
    """
    def __init__(
        self, 
        config_class: Type[T],
        config_path: Path,
        default_config_path: Optional[Path] = None
    ):
        self.config_class = config_class
        self.config_path = config_path
        self.default_config_path = default_config_path
        self._config: Optional[T] = None
        self._lock = threading.RLock()
        
    def get_config(self) -> T:
        """Get the current configuration, loading it if necessary."""
        with self._lock:
            if self._config is None:
                self._load_config()
            return self._config
            
    def update_config(self, new_config: Dict[str, Any]) -> T:
        """Update the configuration with new values."""
        with self._lock:
            # Parse and validate with Pydantic
            updated_config = self.config_class.model_validate(new_config)
            
            # Save to disk
            with open(self.config_path, 'w') as f:
                json.dump(updated_config.model_dump(), f, indent=2)
                
            self._config = updated_config
            return self._config
            
    def update_section(self, section: str, section_data: Dict[str, Any]) -> T:
        """Update a specific section of the configuration."""
        with self._lock:
            current = self.get_config().model_dump()
            current[section] = section_data
            return self.update_config(current)
    
    def reset_to_defaults(self) -> T:
        """Reset configuration to defaults."""
        with self._lock:
            if not self.default_config_path or not self.default_config_path.exists():
                # No defaults available, create empty config
                self._config = self.config_class()
                return self._config
                
            # Load defaults
            with open(self.default_config_path, 'r') as f:
                config_data = json.load(f)
            
            # Update config
            return self.update_config(config_data)
            
    def _load_config(self) -> None:
        """Load configuration from file, falling back to defaults if needed."""
        try:
            # Try to load custom config
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config_data = json.load(f)
                self._config = self.config_class.model_validate(config_data)
                logger.info(f"Loaded configuration from {self.config_path}")
                return
                
            # Fall back to default if available
            if self.default_config_path and self.default_config_path.exists():
                with open(self.default_config_path, 'r') as f:
                    config_data = json.load(f)
                self._config = self.config_class.model_validate(config_data)
                logger.info(f"Loaded default configuration from {self.default_config_path}")
                return
                
            # No config found, create empty
            logger.warning("No configuration found, creating empty config")
            self._config = self.config_class()
            
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            # Create empty config on error
            self._config = self.config_class()