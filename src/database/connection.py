"""Database connection management."""
import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

DATABASE_PATH = Path(__file__).parent.parent.parent / "data" / "negotiate.db"

# Global connection pool (single connection for SQLite)
_db: aiosqlite.Connection | None = None


async def init_db() -> None:
    """Initialize database connection."""
    global _db
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(DATABASE_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA foreign_keys = ON")


async def close_db() -> None:
    """Close database connection."""
    global _db
    if _db:
        await _db.close()
        _db = None


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Get database connection."""
    if _db is None:
        await init_db()
    yield _db  # type: ignore
