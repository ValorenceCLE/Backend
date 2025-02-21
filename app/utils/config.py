from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App settings
    APP_NAME: str = 'FastAPI App'

    # JWT settings
    SECRET_KEY: str = 'your_secret_key'
    ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # User settings
    USER_USERNAME: str = 'default_user'
    USER_PASSWORD: str = 'default_password'

    # Admin settings
    ADMIN_USERNAME: str = 'admin_user'
    ADMIN_PASSWORD: str = 'admin_password'

    class Config:
        env_file = 'settings.env'
        env_file_encoding = 'utf-8'
        extra = 'ignore'

settings = Settings()
