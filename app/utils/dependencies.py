from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.core.env_settings import env


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
# Create an OAuth2 scheme that does not automatically raise an error.
oauth2_scheme_internal = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Verifies JWT token and returns user payload.
    """
    try:
        payload = jwt.decode(token, env.SECRET_KEY, algorithms=[env.ALGORITHM])
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

async def verify_token_ws(token: str):
    """
    Verifies JWT token for WebSocket connections.
    Similar to get_current_user but doesn't use Depends.
    """
    try:
        payload = jwt.decode(token, env.SECRET_KEY, algorithms=[env.ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None or role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )
        return {"username": username, "role": role}
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )

def require_role(required_roles):
    """
    Dependency to enforce role-based access control.
    Accepts either a single role (str) or a list of allowed roles.
    """
    async def role_checker(user=Depends(get_current_user)):
        if isinstance(required_roles, str):
            allowed = [required_roles]
        else:
            allowed = required_roles

        if user["role"] not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied for role: {user['role']}",
            )
        return user
    return role_checker

async def is_admin(user: dict = Depends(get_current_user)) -> bool:
    """
    Checks if the authenticated user has an admin role.
    Returns True if the user's role is 'admin', otherwise raises an HTTPException.
    """
    if user.get("role") == "admin":
        return True
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Admins only",
        )

async def is_user(user: dict = Depends(get_current_user)) -> bool:
    """
    Checks if the authenticated user has a user role.
    Returns True if the user's role is 'user', otherwise raises an HTTPException.
    """
    if user.get("role") == "user":
        return True
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Users only",
        )
    
async def is_authenticated(token: str = Depends(oauth2_scheme)) -> bool:
    """
    Checks if the user is authenticated by validating the JWT token.
    Returns True if valid, otherwise raises an HTTPException.
    """
    try:
        payload = jwt.decode(token, env.SECRET_KEY, algorithms=[env.ALGORITHM])
        return True
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    

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
    INTERNAL_API_KEY = env.SECRET_KEY
    
    # Check for the internal key first.
    if x_internal_api_key == INTERNAL_API_KEY:
        # Internal call: bypass token-based auth.
        return {"username": "internal", "role": "admin", "internal": True}
    
    # No (valid) internal key provided, so fall back to token-based auth.
    if token:
        try:
            payload = jwt.decode(token, env.SECRET_KEY, algorithms=[env.ALGORITHM])
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
