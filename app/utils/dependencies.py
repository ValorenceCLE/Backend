from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
try:
    from app.utils.config import settings
except ImportError:
    from utils.config import settings

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

        # Debug logging - you can remove this later
        print(f"[DEBUG] User role: {user.get('role')}, Allowed: {allowed}")
        
        if user["role"] not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied for role: {user['role']}",
            )
        return user
    return role_checker
