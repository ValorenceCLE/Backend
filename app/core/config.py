from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App settings
    APP_NAME: str = 'FastAPI App'

    # JWT settings
    SECRET_KEY: str
    ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # User settings
    USER_USERNAME: str
    USER_PASSWORD: str

    # Admin settings
    ADMIN_USERNAME: str
    ADMIN_PASSWORD: str

    class Config:
        env_file = 'settings.env'
        env_file_encoding = 'utf-8'
        extra = 'ignore'

settings = Settings()
