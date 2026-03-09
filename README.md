# NegotiateAI Backend

Multi-Agent Negotiation System - AI agents that negotiate deals in parallel.

Built for the Lanesurf Agent Engineer portfolio.

## Tech Stack
- **FastAPI** - Modern async Python web framework
- **Pydantic AI** - Type-safe AI agent framework
- **OpenAI GPT-4o** - LLM for negotiation intelligence

## Local Development

```bash
# Install dependencies with uv
uv sync

# Set your OpenAI API key
export OPENAI_API_KEY=sk-your-key-here

# Run the server
PYTHONPATH=. uv run uvicorn src.main:app --reload --port 8000
```

## API Endpoints

- `POST /api/negotiate` - Start a new negotiation session
- `GET /api/negotiate/{session_id}` - Get session status
- `GET /api/negotiate/{session_id}/stream` - Stream real-time updates (SSE)

## Environment Variables

- `OPENAI_API_KEY` - Your OpenAI API key (required)
