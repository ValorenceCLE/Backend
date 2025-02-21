from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from pydantic import BaseModel

from core.config import settings
from core.security import verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])

class Token(BaseModel):
    access_token: str
    token_type: str

def authenticate_user(username: str, password: str) -> dict:
    """
    Authenticate the user against the credentials stored in settings.
    Returns a dict with user info if successful; otherwise, None.
    """
    # Check against the demo user
    if username == settings.USER_USERNAME and verify_password(password, settings.USER_PASSWORD):
        return {"username": username, "role": "user"}
    # Check against the demo admin
    if username == settings.ADMIN_USERNAME and verify_password(password, settings.ADMIN_PASSWORD):
        return {"username": username, "role": "admin"}
    return None

@router.post("/login", response_model=Token, summary="User login and JWT token retrieval")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Login endpoint that verifies user credentials and returns a JWT token.
    The frontend (Vue) should send credentials as form data (with keys 'username' and 'password').
    
    **Note:** If you prefer a JSON payload, you can create an alternative endpoint using a Pydantic model.
    """
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout", summary="User logout")
def logout():
    """
    Since JWT is stateless, logout can be handled on the client by simply
    deleting the token. This endpoint is a placeholder if you wish to implement
    token revocation/blacklisting in the future.
    """
    return {"message": "Logout successful"}
