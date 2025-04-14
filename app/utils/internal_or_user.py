import os
from fastapi import Header, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.utils.config import settings

# Create an OAuth2 scheme that does not automatically raise an error.
oauth2_scheme_internal = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

async def internal_or_user_auth(
    x_internal_api_key: str = Header(None),
    token: str = Depends(oauth2_scheme_internal)
):
    """
    Combined authentication dependency that:
      - If the request includes a valid internal header (X-Internal-API-Key), it returns
        a dummy internal user.
      - Otherwise, it falls back to verifying the provided JWT token.
    """
    INTERNAL_API_KEY = settings.SECRET_KEY
    
    # Check for the internal key first.
    if x_internal_api_key == INTERNAL_API_KEY:
        # Internal call: bypass token-based auth.
        return {"username": "internal", "role": "admin", "internal": True}
    
    # No (valid) internal key provided, so fall back to token-based auth.
    if token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            username: str = payload.get("sub")
            role: str = payload.get("role")
            if username is None or role is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return {"username": username, "role": role}
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Could not validate credentials",
            )
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
