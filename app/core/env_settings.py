# app/core/env_settings.py
from pydantic_settings import BaseSettings
from pydantic import ValidationError
from pathlib import Path
from typing import Dict, List, Any

def get_env_path() -> Path:
    try:
        BASE_DIR = Path(__file__).resolve().parents[2]
        ENV_PATH = BASE_DIR / 'secrets' / 'app.env'
        if not ENV_PATH.exists():
            # Fallback to common Docker environment paths
            ENV_PATH = Path('/app/secrets/app.env')
            if not ENV_PATH.exists():
                ENV_PATH = Path('/app/app.env')

    except (NameError, ValueError, ValidationError):
        BASE_DIR = Path('/app')
        ENV_PATH = BASE_DIR / 'app.env'
    return ENV_PATH

class EnvSettings(BaseSettings):
    APP_NAME: str = 'CM5'
    SECRET_KEY: str = 'your_secret_key'
    ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    USER_USERNAME: str = 'user'
    HASHED_USER_PASSWORD: str = ""

    ADMIN_USERNAME: str = 'admin'
    HASHED_ADMIN_PASSWORD: str = ""
    LOG_FILES: Dict[str, str] = {
    "camera": "/var/log/camera.log",
    "router": "/var/log/router.log"
    }
    CAMERA_LOG_FILE: str = LOG_FILES["camera"]
    ROUTER_LOG_FILE: str = LOG_FILES["router"]
    # InfluxDB settings
    INFLUXDB_URL: str = 'http://influxdb:8086'
    ORG: str = 'RPi'
    BUCKET: str = 'Raw_Data'
    
    # Config
    CONFIG_FILE: str = 'app/config/config.json'
    CUSTOM_CONFIG_FILE: str = 'app/config/custom_config.json'
    SSL_CERT_FILE: Path = Path("/app/certs/deviceCert.crt")
    SSL_KEY_FILE: Path = Path("/app/certs/deviceCert.key")

    # GPIO settings
    HARDWARE_CONFIG: Dict[str, Dict[str, Any]] = {
        "relay_1": {"pin": 22, "normally": "closed"},  # Camera Disable
        "relay_2": {"pin": 27, "normally": "closed"},  # Router Disable
        "relay_3": {"pin": 17, "normally": "open"},    # Enable
        "relay_4": {"pin": 4,  "normally": "open"},    # Enable
        "relay_5": {"pin": 24, "normally": "open"},    # Enable
        "relay_6": {"pin": 23, "normally": "open"},    # Enable
    }
    GPIO_CHIP: str = "/dev/gpiochip0"

    # Sensor settings
    INA260_SENSORS: List[Dict[str, Any]] = [
        {"relay_id": "relay_1", "address": 0x44},
        {"relay_id": "relay_2", "address": 0x45},
        {"relay_id": "relay_3", "address": 0x46},
        {"relay_id": "relay_4", "address": 0x47},
        {"relay_id": "relay_5", "address": 0x48},
        {"relay_id": "relay_6", "address": 0x49},
        {"relay_id": "main", "address": 0x4B},
    ]

    # Schedule Bitmask
    DAY_BITMASK: Dict[str, int] = {
        "Sunday": 2,
        "Monday": 4,
        "Tuesday": 8,
        "Wednesday": 16,
        "Thursday": 32,
        "Friday": 64,
        "Saturday": 128
    }

    # Redis settings
    REDIS_URL: str = 'redis://redis:6379'
    
    # Additional InfluxDB init settings
    DOCKER_INFLUXDB_INIT_MODE: str = 'setup'
    DOCKER_INFLUXDB_INIT_USERNAME: str = 'admin'
    DOCKER_INFLUXDB_INIT_PASSWORD: str = ''
    DOCKER_INFLUXDB_INIT_ADMIN_TOKEN: str = ''

    @property
    def default_config_path(self) -> Path:
        """Get the default configuration path as a Path object."""
        return Path(self.CONFIG_FILE)
    
    @property
    def custom_config_path(self) -> Path:
        """Get the custom configuration path as a Path object."""
        return Path(self.CUSTOM_CONFIG_FILE)
    
    @property
    def HARDWARE_RELAYS(self):
        """Alias for HARDWARE_CONFIG for backward compatibility."""
        return self.HARDWARE_CONFIG

    class Config:
        env_file = str(get_env_path())
        env_file_encoding = 'utf-8'
        extra = 'ignore'
        
        # Allow environment variables to override values in the env file
        env_nested_delimiter = '__'
        
        # Debug settings loading
        validate_assignment = True

# Create a singleton instance
env = EnvSettings()