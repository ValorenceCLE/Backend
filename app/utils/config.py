from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path('/app')
ENV_PATH = BASE_DIR / 'settings.env'

class Settings(BaseSettings):
    APP_NAME: str = 'FastAPI App'
    SECRET_KEY: str = 'your_secret_key'
    ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 360

    USER_USERNAME: str = 'user'
    HASHED_USER_PASSWORD: str

    ADMIN_USERNAME: str = 'admin'
    HASHED_ADMIN_PASSWORD: str

    class Config:
        env_file = str('/settings.env')
        env_file_encoding = 'utf-8'
        extra = 'ignore'

settings = Settings()
