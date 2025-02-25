from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from pydantic import BaseModel
import logging

from app.utils.config import settings
from app.utils.security import authenticate_user, create_access_token

# ✅ Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class Token(BaseModel):
    access_token: str
    token_type: str


@router.post("/login", response_model=Token, summary="User login and JWT token retrieval")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Login endpoint that verifies user credentials and returns a JWT token.
    """
    logger.info(f"🔓 Login attempt for user: {form_data.username}")
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        logger.info(f"❌ Invalid login credentials for user: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = await create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=access_token_expires
    )
    logger.info(f"✅ Login successful for user: {user['username']} - Token generated.")
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout", summary="User logout")
async def logout():
    """
    Logout endpoint placeholder.
    """
    logger.info(f"🔒 Logout requested.")
    return {"message": "Logout successful"}
