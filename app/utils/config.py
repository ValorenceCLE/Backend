from pydantic_settings import BaseSettings
from pydantic import ValidationError
from pathlib import Path

def get_env_path() -> Path:
    try:
        BASE_DIR = Path(__file__).resolve().parents[2]
        ENV_PATH = BASE_DIR / 'secrets' / 'app.env'  # Changed from settings.env
        if not ENV_PATH.exists():
            # Fallback to common Docker environment paths
            ENV_PATH = Path('/app/secrets/app.env')  # Changed from settings.env
            if not ENV_PATH.exists():
                ENV_PATH = Path('/app/app.env')  # Changed from settings.env

    except NameError or ValueError or ValidationError:
        BASE_DIR = Path('/app')
        ENV_PATH = BASE_DIR / 'app.env'  # Changed from settings.env
    return ENV_PATH

class Settings(BaseSettings):
    APP_NAME: str = 'CM5'
    SECRET_KEY: str = 'your_secret_key'
    ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    USER_USERNAME: str = 'user'
    HASHED_USER_PASSWORD: str = ""

    ADMIN_USERNAME: str = 'admin'
    HASHED_ADMIN_PASSWORD: str = ""

    # InfluxDB settings
    INFLUXDB_URL: str = 'http://influxdb:8086'
    ORG: str = 'RPi'
    BUCKET: str = 'Raw_Data'
    
    # Redis settings
    REDIS_URL: str = 'redis://redis:6379'
    
    # Additional InfluxDB init settings
    DOCKER_INFLUXDB_INIT_MODE: str = 'setup'
    DOCKER_INFLUXDB_INIT_USERNAME: str = 'admin'
    DOCKER_INFLUXDB_INIT_PASSWORD: str = ''
    DOCKER_INFLUXDB_INIT_ADMIN_TOKEN: str = ''

    class Config:
        env_file = str(get_env_path())
        env_file_encoding = 'utf-8'
        extra = 'ignore'
        
        # Allow environment variables to override values in the env file
        env_nested_delimiter = '__'
        
        # Debug settings loading
        validate_assignment = True

settings = Settings()
