import logging
from datetime import datetime, timedelta
from jose import jwt, JWTError
from app.utils.hashing import verify_password
from app.utils.config import settings

# ✅ Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def authenticate_user(username: str, password: str) -> dict:
    """
    Authenticate user against hashed credentials stored in settings.
    """
    logger.info(f"🔑 Attempting authentication for user: {username}")
    if username == settings.USER_USERNAME and await verify_password(password, settings.HASHED_USER_PASSWORD):
        logger.info(f"✅ User '{username}' authenticated successfully (role: user).")
        return {"username": username, "role": "user"}

    if username == settings.ADMIN_USERNAME and await verify_password(password, settings.HASHED_ADMIN_PASSWORD):
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
        expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        logger.info(f"🔒 JWT created for user {data['sub']} with expiration at {expire}")
        return encoded_jwt
    except JWTError as e:
        logger.error(f"❌ Error creating access token: {e}")
        return None
