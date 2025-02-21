from pathlib import Path
from pydantic_settings import BaseSettings
import os
from dotenv import load_dotenv

class Settings(BaseSettings):
    load_dotenv(dotenv_path='config\.env')

    # App settings
    APP_NAME: str = os.getenv('APP_NAME', 'FastAPI App')

    # JWT settings
    SECRET_KEY: str = os.getenv('SECRET_KEY')
    ALGORITHM: str = os.getenv('ALGORITHM', 'HS256')
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 30))

    # User settings
    USER_USERNAME: str = os.getenv('USER_USERNAME')
    USER_PASSWORD: str = os.getenv('USER_PASSWORD')

    # Admin settings
    ADMIN_USERNAME: str = os.getenv('ADMIN_USERNAME')
    ADMIN_PASSWORD: str = os.getenv('ADMIN_PASSWORD')

settings = Settings()
