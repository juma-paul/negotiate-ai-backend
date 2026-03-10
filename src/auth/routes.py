"""Authentication API routes."""
import secrets
import json
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from .password import hash_password, verify_password
from .jwt import create_access_token
from .dependencies import require_auth
from ..database.connection import get_db
from ..config import logger

router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    """Registration request."""
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)


class LoginRequest(BaseModel):
    """Login request."""
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    """Authentication response with token."""
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    """User profile response."""
    id: str
    email: str
    created_at: str
    preferences: dict


class PreferencesUpdate(BaseModel):
    """User preferences update."""
    default_strategy: str | None = None
    default_num_providers: int | None = Field(None, ge=1, le=10)


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """Register a new user account."""
    async with get_db() as db:
        # Check if email already exists
        cursor = await db.execute(
            "SELECT id FROM users WHERE email = ?", (request.email,)
        )
        if await cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Create user
        user_id = secrets.token_urlsafe(16)
        password_hash = hash_password(request.password)

        await db.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (user_id, request.email, password_hash)
        )
        await db.commit()

        logger.info(f"New user registered: {request.email}")

        # Generate token
        token = create_access_token(user_id, request.email)

        return AuthResponse(
            access_token=token,
            user={
                "id": user_id,
                "email": request.email,
                "preferences": {},
            }
        )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """Login with email and password."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, email, password_hash, preferences FROM users WHERE email = ?",
            (request.email,)
        )
        row = await cursor.fetchone()

        if not row or not verify_password(request.password, row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        logger.info(f"User logged in: {request.email}")

        token = create_access_token(row["id"], row["email"])
        preferences = json.loads(row["preferences"]) if row["preferences"] else {}

        return AuthResponse(
            access_token=token,
            user={
                "id": row["id"],
                "email": row["email"],
                "preferences": preferences,
            }
        )


@router.get("/me", response_model=UserResponse)
async def get_me(user: Annotated[dict, Depends(require_auth)]):
    """Get current user profile."""
    preferences = json.loads(user["preferences"]) if user["preferences"] else {}
    return UserResponse(
        id=user["id"],
        email=user["email"],
        created_at=user["created_at"],
        preferences=preferences,
    )


@router.patch("/preferences")
async def update_preferences(
    updates: PreferencesUpdate,
    user: Annotated[dict, Depends(require_auth)]
):
    """Update user preferences."""
    async with get_db() as db:
        # Get current preferences
        cursor = await db.execute(
            "SELECT preferences FROM users WHERE id = ?", (user["id"],)
        )
        row = await cursor.fetchone()
        current = json.loads(row["preferences"]) if row and row["preferences"] else {}

        # Update with new values
        if updates.default_strategy is not None:
            current["default_strategy"] = updates.default_strategy
        if updates.default_num_providers is not None:
            current["default_num_providers"] = updates.default_num_providers

        # Save
        await db.execute(
            "UPDATE users SET preferences = ? WHERE id = ?",
            (json.dumps(current), user["id"])
        )
        await db.commit()

        return {"message": "Preferences updated", "preferences": current}
