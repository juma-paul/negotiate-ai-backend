"""FastAPI backend for NegotiateAI - Production-ready with security."""
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from .models import NegotiationRequest, NegotiationSession
from .orchestrator import create_session, run_negotiations, get_session
from .config import get_settings, logger

# Rate limiting (simple in-memory) - more permissive
_request_counts: dict[str, list[float]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan with startup validation."""
    settings = get_settings()
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set - agents will fail")
    logger.info(f"Starting NegotiateAI | CORS: {settings.allowed_origins}")
    yield
    logger.info("Shutting down NegotiateAI")


app = FastAPI(
    title="NegotiateAI",
    description="Multi-Agent Negotiation System",
    version="2.0.0",
    lifespan=lifespan
)

# CORS - allow frontend
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins + ["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
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
    return {
        "status": "healthy",
        "openai_configured": bool(settings.openai_api_key),
        "model": settings.openai_model
    }


@app.post("/api/negotiate", response_model=NegotiationSession)
async def start_negotiation(request: NegotiationRequest, req: Request):
    """Start new negotiation session."""
    ip = req.client.host if req.client else "unknown"
    try:
        session = await create_session(request)
        logger.info(f"Session {session.session_id} created by {ip}")
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
    session.status = "cancelled"
    logger.info(f"Session {session_id} cancelled")
    return {"status": "cancelled", "session_id": session_id}
