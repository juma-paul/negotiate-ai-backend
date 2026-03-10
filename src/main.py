"""FastAPI backend for NegotiateAI - Production-ready with security."""
import json
import asyncio
from typing import Annotated
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from .models import NegotiationRequest, NegotiationSession
from .orchestrator import create_session, run_negotiations, get_session, cancel_session
from .config import get_settings, logger
from .auth.dependencies import get_current_user, require_auth
from .repositories import SessionRepo
from .database import init_db, create_tables, seed_companies
from .database.connection import close_db
from .auth import auth_router
from .voice import voice_router

# Rate limiting (simple in-memory) - more permissive
_request_counts: dict[str, list[float]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan with startup validation and database init."""
    settings = get_settings()

    # Initialize database
    await init_db()
    await create_tables()
    company_count = await seed_companies()
    logger.info(f"Database initialized with {company_count} companies")

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set - agents will fail")
    if settings.twilio_account_sid:
        logger.info("Twilio configured for voice calls")

    logger.info(f"Starting NegotiateAI | CORS: {settings.allowed_origins}")
    yield

    # Cleanup
    await close_db()
    logger.info("Shutting down NegotiateAI")


app = FastAPI(
    title="NegotiateAI",
    description="Multi-Agent Negotiation System",
    version="2.0.0",
    lifespan=lifespan
)

# Include routers
app.include_router(auth_router)
app.include_router(voice_router)

# CORS - allow frontend
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins + ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)


def check_rate_limit(ip: str, limit: int = 60, window: int = 60) -> bool:
    """Rate limiter - 60 requests per minute per IP (more permissive)."""
    import time
    now = time.time()
    if ip not in _request_counts:
        _request_counts[ip] = []
    _request_counts[ip] = [t for t in _request_counts[ip] if now - t < window]
    if len(_request_counts[ip]) >= limit:
        return False
    _request_counts[ip].append(now)
    return True


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware - only for POST requests."""
    ip = request.client.host if request.client else "unknown"
    # Only rate limit POST (session creation), not GET (status checks)
    if request.method == "POST" and request.url.path.startswith("/api/"):
        if not check_rate_limit(ip, limit=10, window=60):  # 10 new sessions/min
            logger.warning(f"Rate limit exceeded for {ip}")
            return JSONResponse(status_code=429, content={"detail": "Too many requests"})
    return await call_next(request)


@app.get("/")
async def root():
    """Health check."""
    return {"status": "healthy", "service": "NegotiateAI", "version": "2.0.0"}


@app.get("/health")
async def health():
    """Detailed health check."""
    settings = get_settings()
    from .database.connection import get_db
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM companies")
        row = await cursor.fetchone()
        company_count = row[0] if row else 0
    return {
        "status": "healthy",
        "openai_configured": bool(settings.openai_api_key),
        "twilio_configured": bool(settings.twilio_account_sid),
        "model": settings.openai_model,
        "companies_loaded": company_count,
    }


@app.get("/api/companies")
async def list_companies():
    """List all available trucking companies (public info only)."""
    from .database.connection import get_db
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, name, contact_phone, service_areas, fleet_info,
                      personality, rating, is_active
               FROM companies WHERE is_active = 1
               ORDER BY rating DESC"""
        )
        rows = await cursor.fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "phone": row["contact_phone"],
            "service_areas": json.loads(row["service_areas"]),
            "fleet_info": json.loads(row["fleet_info"]),
            "personality": row["personality"],
            "rating": row["rating"],
        }
        for row in rows
    ]


@app.post("/api/negotiate", response_model=NegotiationSession)
async def start_negotiation(
    request: NegotiationRequest,
    req: Request,
    user: Annotated[dict | None, Depends(get_current_user)] = None
):
    """Start new negotiation session. Optionally authenticated for history tracking."""
    ip = req.client.host if req.client else "unknown"
    user_id = user["id"] if user else None
    try:
        session = await create_session(request, user_id=user_id)
        logger.info(f"Session {session.session_id} created by {ip} (user: {user_id or 'anonymous'})")
        return session
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Session creation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session")


@app.get("/api/negotiate/{session_id}")
async def get_negotiation(session_id: str):
    """Get session state."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    # Don't expose min_price to clients
    response = session.model_dump()
    for p in response["providers"]:
        p.pop("min_price", None)
    return response


@app.get("/api/negotiate/{session_id}/stream")
async def stream_negotiation(session_id: str):
    """Stream negotiation updates with heartbeat."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator():
        try:
            async for update in run_negotiations(session_id):
                yield {"event": update.event_type, "data": json.dumps(update.model_dump())}
        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for {session_id}")
        except Exception as e:
            logger.error(f"Stream error for {session_id}: {e}")
            yield {"event": "error", "data": json.dumps({"error": "Stream failed"})}

    return EventSourceResponse(
        event_generator(),
        ping=15,
        ping_message_factory=lambda: {"event": "ping", "data": "{}"}
    )


@app.delete("/api/negotiate/{session_id}")
async def cancel_negotiation(session_id: str):
    """Cancel session."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await cancel_session(session_id)
    return {"status": "cancelled", "session_id": session_id}


@app.get("/api/history")
async def get_history(user: Annotated[dict, Depends(require_auth)]):
    """Get user's negotiation history."""
    sessions = await SessionRepo.get_user_sessions(user["id"])
    return {"sessions": sessions}


@app.get("/api/analytics")
async def get_analytics(user: Annotated[dict, Depends(require_auth)]):
    """Get user's savings analytics."""
    from .database.connection import get_db
    async with get_db() as db:
        # Get overall stats
        cursor = await db.execute(
            """SELECT
                COUNT(*) as total_negotiations,
                COALESCE(SUM(savings_amount), 0) as total_savings,
                COALESCE(AVG(savings_percent), 0) as avg_savings_percent,
                COALESCE(AVG(rounds_taken), 0) as avg_rounds
               FROM negotiation_results WHERE user_id = ?""",
            (user["id"],)
        )
        stats = dict(await cursor.fetchone())

        # Get by strategy
        cursor = await db.execute(
            """SELECT strategy, COUNT(*) as count,
                      COALESCE(AVG(savings_percent), 0) as avg_savings
               FROM negotiation_results WHERE user_id = ?
               GROUP BY strategy""",
            (user["id"],)
        )
        by_strategy = [dict(row) for row in await cursor.fetchall()]

        # Get recent results
        cursor = await db.execute(
            """SELECT r.*, c.name as company_name
               FROM negotiation_results r
               JOIN companies c ON r.company_id = c.id
               WHERE r.user_id = ?
               ORDER BY r.created_at DESC LIMIT 10""",
            (user["id"],)
        )
        recent = [dict(row) for row in await cursor.fetchall()]

    return {
        "stats": {
            "total_negotiations": stats["total_negotiations"],
            "total_savings": round(stats["total_savings"], 2),
            "avg_savings_percent": round(stats["avg_savings_percent"], 1),
            "avg_rounds": round(stats["avg_rounds"], 1),
        },
        "by_strategy": by_strategy,
        "recent_results": recent,
    }
