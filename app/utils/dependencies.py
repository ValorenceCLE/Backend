from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.utils.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Verifies JWT token and returns user payload.
    """
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

async def verify_token_ws(token: str):
    """
    Verifies JWT token for WebSocket connections.
    Similar to get_current_user but doesn't use Depends.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
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
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return True
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )