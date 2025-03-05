from pydantic_settings import BaseSettings
from pathlib import Path
import os
from dotenv import load_dotenv

if os.environ.get("ENV_FILE"):
    ENV_PATH = Path(os.environ.get("ENV_FILE"))
elif os.path.exists('/.dockerenv'):
    ENV_PATH = Path('/settings.env')
else:
    BASE_DIR = Path(__file__).resolve().parents[2]
    ENV_PATH = BASE_DIR / 'secrets' / 'settings.env'

if not ENV_PATH.exists():
    raise FileNotFoundError(f"Environment file not found at: {ENV_PATH}")

# Optionally, load environment variables into os.environ
load_dotenv(dotenv_path=ENV_PATH)

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
        env_file = str(ENV_PATH)
        env_file_encoding = 'utf-8'
        extra = 'ignore'

settings = Settings()
