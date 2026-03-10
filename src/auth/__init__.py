"""Authentication module for NegotiateAI."""
from .password import hash_password, verify_password
from .jwt import create_access_token, decode_token
from .dependencies import get_current_user, require_auth
from .routes import router as auth_router

__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_token",
    "get_current_user",
    "require_auth",
    "auth_router",
]
