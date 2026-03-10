"""FastAPI dependencies for authentication."""
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .jwt import decode_token
from ..database.connection import get_db

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)]
) -> dict | None:
    """Get current user from JWT token. Returns None if not authenticated."""
    if not credentials:
        return None

    payload = decode_token(credentials.credentials)
    if not payload:
        return None

    # Verify user exists in database
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, email, created_at, preferences FROM users WHERE id = ?",
            (payload["sub"],)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        return {
            "id": row["id"],
            "email": row["email"],
            "created_at": row["created_at"],
            "preferences": row["preferences"],
        }


async def require_auth(
    user: Annotated[dict | None, Depends(get_current_user)]
) -> dict:
    """Require authentication. Raises 401 if not authenticated."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
