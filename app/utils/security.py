import logging
from datetime import datetime, timedelta
from jose import jwt, JWTError
from app.utils.hashing import verify_password
from app.core.env_settings import env


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set to DEBUG for more verbose logging

async def authenticate_user(username: str, password: str) -> dict:
    """
    Authenticate user against hashed credentials stored in settings.
    """
    logger.info(f"🔑 Attempting authentication for user: {username}")
    if username == env.USER_USERNAME and await verify_password(password, env.HASHED_USER_PASSWORD):
        logger.info(f"✅ User '{username}' authenticated successfully (role: user).")
        return {"username": username, "role": "user"}

    if username == env.ADMIN_USERNAME and await verify_password(password, env.HASHED_ADMIN_PASSWORD):
        logger.info(f"✅ Admin '{username}' authenticated successfully (role: admin).")
        return {"username": username, "role": "admin"}

    logger.warning(f"⚠️ Failed authentication attempt for user: {username}")
    return None


async def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """
    Create a JWT access token.
    """
    try:
        to_encode = data.copy()
        expire = datetime.utcnow() + (expires_delta or timedelta(minutes=env.ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, env.SECRET_KEY, algorithm=env.ALGORITHM)
        logger.info(f"🔒 JWT created for user {data['sub']} with expiration at {expire}")
        return encoded_jwt
    except JWTError as e:
        logger.error(f"❌ Error creating access token: {e}")
        return None
