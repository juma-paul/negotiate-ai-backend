"""FastAPI backend for NegotiateAI - Multi-Agent Negotiation System."""
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import json

from .models import NegotiationRequest, NegotiationSession
from .orchestrator import create_session, run_parallel_negotiations, get_session

# Load environment variables
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Verify OpenAI API key is set
    if not os.getenv("OPENAI_API_KEY"):
        print("WARNING: OPENAI_API_KEY not set!")
    yield

app = FastAPI(
    title="NegotiateAI",
    description="Multi-Agent Negotiation System - AI agents that negotiate deals in parallel",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your Vercel domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "running",
        "service": "NegotiateAI",
        "version": "1.0.0"
    }


@app.post("/api/negotiate", response_model=NegotiationSession)
async def start_negotiation(request: NegotiationRequest):
    """Start a new negotiation session with multiple providers."""
    try:
        session = await create_session(request)
        return session
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/negotiate/{session_id}")
async def get_negotiation(session_id: str):
    """Get the current state of a negotiation session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/api/negotiate/{session_id}/stream")
async def stream_negotiation(session_id: str):
    """Stream negotiation updates in real-time using Server-Sent Events."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator():
        async for update in run_parallel_negotiations(session_id):
            yield {
                "event": update.event_type,
                "data": json.dumps(update.model_dump())
            }

    return EventSourceResponse(event_generator())


@app.delete("/api/negotiate/{session_id}")
async def cancel_negotiation(session_id: str):
    """Cancel an ongoing negotiation session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.status = "cancelled"
    return {"status": "cancelled", "session_id": session_id}


# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
