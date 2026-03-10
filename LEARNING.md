# NegotiateAI - Learning Guide

A step-by-step tutorial to understand and recreate this multi-agent negotiation system.

---

## Table of Contents

1. [Understanding the Architecture](#1-understanding-the-architecture)
2. [Backend Deep Dive](#2-backend-deep-dive)
3. [Frontend Deep Dive](#3-frontend-deep-dive)
4. [Building It Yourself](#4-building-it-yourself)
5. [Key Concepts Explained](#5-key-concepts-explained)

---

## 1. Understanding the Architecture

### What Does This System Do?

NegotiateAI deploys **multiple AI agents** to negotiate with **multiple providers** simultaneously. Think of it as having 5 expert negotiators working for you at the same time, each talking to a different vendor, all trying to get you the best price.

```
┌──────────────────────────────────────────────────────────────┐
│                     You (User/Client)                        │
│                Enter: "Freight LA→Chicago, $3000 target"     │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                    React Dashboard                            │
│              Real-time view of all negotiations               │
└───────────────────────────┬──────────────────────────────────┘
                            │ SSE (Server-Sent Events)
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                   FastAPI Backend                             │
│   ┌────────────────────────────────────────────────────────┐ │
│   │              Orchestrator (coordinates all)             │ │
│   └────────────────────────────────────────────────────────┘ │
│          │              │              │              │      │
│   ┌──────▼───┐   ┌──────▼───┐   ┌──────▼───┐   ┌──────▼───┐ │
│   │ Agent 1  │   │ Agent 2  │   │ Agent 3  │   │ Agent N  │ │
│   │Negotiator│   │Negotiator│   │Negotiator│   │Negotiator│ │
│   └──────┬───┘   └──────┬───┘   └──────┬───┘   └──────┬───┘ │
│          │              │              │              │      │
│   ┌──────▼───┐   ┌──────▼───┐   ┌──────▼───┐   ┌──────▼───┐ │
│   │Provider A│   │Provider B│   │Provider C│   │Provider N│ │
│   │  (FIRM)  │   │(FLEXIBLE)│   │(DESPERATE│   │(PREMIUM) │ │
│   └──────────┘   └──────────┘   └──────────┘   └──────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### The Data Flow

1. **User submits request** → Target price, max budget, item description
2. **Backend creates session** → Spawns 5 providers with random personalities
3. **Orchestrator runs rounds** → Each round, all agents negotiate in parallel
4. **Real-time updates** → SSE streams every message to the dashboard
5. **Best deal found** → System identifies the lowest accepted price

---

## 2. Backend Deep Dive

### File Structure

```
backend/
├── src/
│   ├── __init__.py          # Package marker
│   ├── config.py            # Settings & logging (START HERE)
│   ├── models.py            # Pydantic data structures
│   ├── negotiator.py        # AI agent that negotiates FOR you
│   ├── providers.py         # Simulated vendors with personalities
│   ├── orchestrator.py      # Coordinates parallel negotiations
│   └── main.py              # FastAPI endpoints
├── tests/
│   ├── test_api.py          # API endpoint tests
│   └── test_models.py       # Model validation tests
├── pyproject.toml           # Dependencies & tooling
└── run.py                   # Entry point
```

### Step-by-Step: config.py

**Purpose**: Centralized configuration and logging.

```python
# ============================================================
# FILE: src/config.py
# PURPOSE: Centralized settings loaded from environment variables
# ============================================================

"""Configuration and logging setup."""
import os
import logging
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """App settings from environment.

    Pydantic Settings automatically reads from:
    1. Environment variables
    2. .env file

    Example .env:
        OPENAI_API_KEY=sk-xxx
        OPENAI_MODEL=gpt-4o-mini
    """

    # API Keys
    openai_api_key: str = ""           # Required for AI agents

    # Model Configuration
    openai_model: str = "gpt-4o-mini"       # Main negotiator
    openai_model_mini: str = "gpt-4o-mini"  # Provider simulation

    # Timeouts and Limits
    api_timeout: int = 30              # Seconds before LLM call fails
    max_rounds: int = 5                # Max negotiation rounds
    sse_heartbeat_interval: int = 15   # Keep connection alive
    session_ttl_seconds: int = 3600    # Clean up old sessions

    # Security
    allowed_origins: list[str] = ["https://frontend-ten-wine-44.vercel.app"]

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"


@lru_cache  # Cache settings (singleton pattern)
def get_settings() -> Settings:
    return Settings()


def setup_logging() -> logging.Logger:
    """Configure structured logging."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logger = logging.getLogger("negotiate-ai")
    return logger


logger = setup_logging()
```

**Key Concepts**:
- `@lru_cache` → Settings loaded once, reused everywhere
- `BaseSettings` → Automatic env variable parsing
- Structured logging → Easy debugging in production

---

### Step-by-Step: models.py

**Purpose**: Define all data structures with validation.

```python
# ============================================================
# FILE: src/models.py
# PURPOSE: Pydantic models for type safety and validation
# ============================================================

"""Pydantic models for the negotiation system."""
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from enum import Enum
import re


# ---- ENUMS: Define allowed values ----

class NegotiationStrategy(str, Enum):
    """How aggressive should the AI be?"""
    AGGRESSIVE = "aggressive"    # Low offers, willing to walk away
    BALANCED = "balanced"        # Fair deals, middle ground
    CONSERVATIVE = "conservative" # Quick deals, less haggling


class ProviderPersonality(str, Enum):
    """How does the provider behave?"""
    FIRM = "firm"           # Hard to negotiate, 5-10% max discount
    FLEXIBLE = "flexible"   # Reasonable, 15-25% discount possible
    DESPERATE = "desperate" # Needs sales, 30-40% discount
    PREMIUM = "premium"     # Justifies high prices, small discounts


# ---- INPUT MODEL: What the user sends ----

class NegotiationRequest(BaseModel):
    """Request to start a negotiation - with validation."""

    item_description: str = Field(..., min_length=5, max_length=500)
    # "..." means required, min/max enforce length

    target_price: float = Field(..., gt=0, le=1_000_000)
    # gt=greater than, le=less than or equal

    max_price: float = Field(..., gt=0, le=1_000_000)

    num_providers: int = Field(default=5, ge=1, le=10)
    # default=5 if not provided

    strategy: NegotiationStrategy = Field(default=NegotiationStrategy.BALANCED)

    @field_validator("item_description")
    @classmethod
    def sanitize_description(cls, v: str) -> str:
        """SECURITY: Remove potential prompt injection patterns."""
        dangerous = ["ignore previous", "disregard", "new instructions", "system:"]
        lower = v.lower()
        for pattern in dangerous:
            if pattern in lower:
                raise ValueError("Invalid content in description")
        # Remove HTML/template characters
        return re.sub(r"[<>{}]", "", v)[:500]

    @field_validator("max_price")
    @classmethod
    def max_gte_target(cls, v: float, info) -> float:
        """Business rule: max_price must be >= target_price."""
        if "target_price" in info.data and v < info.data["target_price"]:
            raise ValueError("max_price must be >= target_price")
        return v


# ---- AI OUTPUT MODELS: Structured responses from LLM ----

class NegotiationAction(BaseModel):
    """What the negotiator AI decides to do.

    This is the STRUCTURED OUTPUT from the LLM.
    Pydantic AI forces the LLM to return this exact shape.
    """
    action: Literal["offer", "counter", "accept", "reject", "ask_question", "walk_away"]
    amount: float | None = Field(default=None, ge=0, le=1_000_000)
    message: str = Field(..., max_length=500)
    reasoning: str = Field(..., max_length=500)  # Why this decision?
    confidence: float = Field(default=0.5, ge=0, le=1)


class ProviderResponse(BaseModel):
    """What the simulated provider responds with."""
    action: Literal["offer", "counter", "accept", "reject", "provide_info"]
    amount: float | None = Field(default=None, ge=0, le=1_000_000)
    message: str = Field(..., max_length=500)
    final: bool = False  # Is this their final offer?


# ---- STATE MODELS: Track the negotiation ----

class NegotiationMessage(BaseModel):
    """Single message in conversation history."""
    role: Literal["negotiator", "provider"]
    action: str
    amount: float | None
    message: str
    timestamp: str


class ProviderNegotiation(BaseModel):
    """State of negotiation with ONE provider."""
    provider_id: str
    provider_name: str
    personality: ProviderPersonality
    initial_price: float
    current_price: float | None = None
    min_price: float = 0      # SECRET! Never exposed to client
    status: Literal["negotiating", "accepted", "rejected", "walked_away", "error"] = "negotiating"
    messages: list[NegotiationMessage] = []
    rounds: int = 0


class NegotiationSession(BaseModel):
    """Overall session tracking ALL providers."""
    session_id: str
    item_description: str
    target_price: float
    max_price: float
    strategy: NegotiationStrategy
    providers: list[ProviderNegotiation] = []
    status: Literal["in_progress", "completed", "cancelled", "error"] = "in_progress"
    best_deal: ProviderNegotiation | None = None
    total_rounds: int = 0
    created_at: str = ""


class NegotiationUpdate(BaseModel):
    """Real-time update sent via SSE."""
    session_id: str
    provider_id: str
    event_type: Literal["message", "status_change", "deal_found", "completed", "heartbeat", "error"]
    data: dict
```

**Key Concepts**:
- `Field(...)` → Validation constraints
- `@field_validator` → Custom validation logic
- `Literal["a", "b"]` → Only these exact values allowed
- Structured outputs → LLM MUST return this shape

---

### Step-by-Step: negotiator.py

**Purpose**: The AI agent that negotiates ON YOUR BEHALF.

```python
# ============================================================
# FILE: src/negotiator.py
# PURPOSE: Pydantic AI agent that negotiates for the user
# ============================================================

"""Pydantic AI Negotiator Agent - the core AI that negotiates on your behalf."""
import asyncio
from pydantic_ai import Agent
from .models import NegotiationAction, NegotiationStrategy
from .config import get_settings, logger

# Singleton pattern - create agent once, reuse
_negotiator_agent: Agent[None, NegotiationAction] | None = None


def get_negotiator_agent() -> Agent[None, NegotiationAction]:
    """Lazy initialization of the negotiator agent.

    Agent[None, NegotiationAction] means:
    - None: No dependencies (could inject database, etc.)
    - NegotiationAction: The structured output type
    """
    global _negotiator_agent

    if _negotiator_agent is None:
        settings = get_settings()

        _negotiator_agent = Agent(
            f'openai:{settings.openai_model}',  # Model to use
            output_type=NegotiationAction,       # Force this output shape
            system_prompt="""Expert negotiator AI. Get the best price for your client.
STRATEGIES: AGGRESSIVE (low offers, walk away), BALANCED (fair deals), CONSERVATIVE (quick deals).
RULES: Never exceed max_price, aim below target, know when to close. Keep messages under 100 words."""
        )

    return _negotiator_agent


async def negotiate_turn(
    item: str,
    target: float,
    max_price: float,
    strategy: NegotiationStrategy,
    provider: str,
    current_price: float,
    history: list[dict],
    latest_msg: str,
    latest_offer: float | None
) -> NegotiationAction:
    """Execute one negotiation turn.

    This is called each round to decide what to do next.
    """
    settings = get_settings()

    # Format conversation history for context
    history_text = "\n".join([
        f"{'You' if m['role'] == 'negotiator' else 'Provider'}: {m['message']}"
        + (f" [${m['amount']}]" if m.get('amount') else "")
        for m in history[-6:]  # Last 6 messages only (prevent drift)
    ])

    # Build the prompt with all context
    prompt = f"""Item: {item} | Target: ${target} | Max: ${max_price} | Strategy: {strategy.value.upper()}
Provider: {provider} | Current price: ${current_price}
History: {history_text or 'None'}
Latest: "{latest_msg}" {f'Offer: ${latest_offer}' if latest_offer else ''}
Your move?"""

    try:
        # Call LLM with timeout
        result = await asyncio.wait_for(
            get_negotiator_agent().run(prompt),
            timeout=settings.api_timeout
        )
        return result.output  # Returns NegotiationAction

    except asyncio.TimeoutError:
        # Fallback if LLM is slow
        logger.warning(f"Negotiator timeout for {provider}")
        return NegotiationAction(
            action="counter",
            amount=target,
            message="I need to think. My offer stands.",
            reasoning="Timeout fallback",
            confidence=0.3
        )
    except Exception as e:
        # Fallback for any error
        logger.error(f"Negotiator error: {e}")
        return NegotiationAction(
            action="ask_question",
            message="Could you clarify your position?",
            reasoning=f"Error recovery: {str(e)[:50]}",
            confidence=0.2
        )


async def create_opening(
    item: str,
    target: float,
    max_price: float,
    strategy: NegotiationStrategy,
    provider: str,
    asking_price: float
) -> NegotiationAction:
    """Create the opening offer.

    First move in negotiation - set the tone.
    """
    settings = get_settings()

    prompt = f"""NEW NEGOTIATION | Item: {item} | Target: ${target} | Max: ${max_price}
Strategy: {strategy.value.upper()} | Provider: {provider} | Asking: ${asking_price}
Make opening offer. AGGRESSIVE: 60-70%, BALANCED: 75-85%, CONSERVATIVE: 85-90% of ask."""

    try:
        result = await asyncio.wait_for(
            get_negotiator_agent().run(prompt),
            timeout=settings.api_timeout
        )
        return result.output

    except asyncio.TimeoutError:
        # Strategy-based fallback
        pct = {"aggressive": 0.65, "balanced": 0.8, "conservative": 0.88}[strategy.value]
        return NegotiationAction(
            action="offer",
            amount=round(asking_price * pct, 2),
            message=f"I'd like to offer ${round(asking_price * pct, 2)} for this.",
            reasoning="Timeout fallback",
            confidence=0.5
        )
    except Exception as e:
        logger.error(f"Opening offer error: {e}")
        return NegotiationAction(
            action="ask_question",
            message="Can you tell me more about your service?",
            reasoning=f"Error: {str(e)[:50]}",
            confidence=0.2
        )
```

**Key Concepts**:
- `Agent[None, NegotiationAction]` → Typed agent with structured output
- `output_type=NegotiationAction` → Forces LLM to return valid JSON
- `asyncio.wait_for()` → Timeout protection
- Fallback responses → System never crashes

---

### Step-by-Step: providers.py

**Purpose**: Simulate different vendors with unique personalities.

```python
# ============================================================
# FILE: src/providers.py
# PURPOSE: Simulated providers with different negotiation behaviors
# ============================================================

"""Simulated providers with different negotiation personalities."""
import random
import asyncio
from pydantic_ai import Agent
from .models import ProviderPersonality, ProviderResponse
from .config import get_settings, logger

# Company names pool
PROVIDER_NAMES = [
    "QuickShip Logistics", "FastFreight Co", "Budget Haulers Inc",
    "Premium Transport", "Lightning Delivery", "Steady Eddie Trucking",
    "CrossCountry Carriers", "Reliable Routes LLC", "Express Lane Shipping",
    "ValueMove Transport"
]

_provider_agent: Agent[None, ProviderResponse] | None = None


def get_provider_agent() -> Agent[None, ProviderResponse]:
    """Lazy init provider agent."""
    global _provider_agent

    if _provider_agent is None:
        settings = get_settings()
        _provider_agent = Agent(
            f'openai:{settings.openai_model_mini}',  # Cheaper model
            output_type=ProviderResponse,
            system_prompt="""You simulate a service provider in a negotiation.
Respond according to personality: FIRM (5-10% discount max), FLEXIBLE (15-25% off),
DESPERATE (30-40% off, accept quickly), PREMIUM (justify high prices, small discounts).
Set 'final'=true for absolute final offer. Keep messages under 100 words."""
        )

    return _provider_agent


def generate_provider(base_price: float, index: int) -> dict:
    """Generate a provider with random personality and pricing.

    Each personality has different price ranges:
    - FIRM: High prices, won't budge much
    - FLEXIBLE: Medium prices, negotiable
    - DESPERATE: Lower prices, eager to close
    - PREMIUM: Highest prices, justifies value
    """
    personality = random.choice(list(ProviderPersonality))

    # (initial_low, initial_high, min_low, min_high)
    multipliers = {
        ProviderPersonality.FIRM: (1.1, 1.3, 0.9, 0.95),
        ProviderPersonality.FLEXIBLE: (1.0, 1.2, 0.75, 0.85),
        ProviderPersonality.DESPERATE: (0.9, 1.1, 0.6, 0.7),
        ProviderPersonality.PREMIUM: (1.2, 1.5, 0.85, 0.95),
    }

    price_low, price_high, min_low, min_high = multipliers[personality]
    initial = base_price * random.uniform(price_low, price_high)
    min_price = base_price * random.uniform(min_low, min_high)

    return {
        "provider_id": f"p{index}",
        "provider_name": PROVIDER_NAMES[index % len(PROVIDER_NAMES)],
        "personality": personality,
        "initial_price": round(initial, 2),
        "min_price": round(min_price, 2),  # SECRET floor price
    }


async def get_provider_response(
    personality: ProviderPersonality,
    initial_price: float,
    min_price: float,      # Provider knows their floor
    current_price: float,
    history: list[dict],
    customer_message: str,
    customer_offer: float | None
) -> ProviderResponse:
    """Get response from simulated provider."""
    settings = get_settings()

    history_text = "\n".join([
        f"{'Customer' if m['role'] == 'negotiator' else 'You'}: {m['message']}"
        for m in history[-4:]
    ])

    prompt = f"""Personality: {personality.value.upper()}
Initial: ${initial_price}, Minimum: ${min_price}, Current: ${current_price}
History: {history_text}
Customer: {customer_message}
Offer: ${customer_offer if customer_offer else 'none'}

If offer >= minimum, accept. If close, counter. If way below, stand firm."""

    try:
        result = await asyncio.wait_for(
            get_provider_agent().run(prompt),
            timeout=settings.api_timeout
        )
        return result.output

    except asyncio.TimeoutError:
        logger.warning(f"Provider response timeout for {personality}")
        return ProviderResponse(
            action="counter",
            amount=current_price * 0.95,
            message="Let me think about that... how about this price?",
            final=False
        )
    except Exception as e:
        logger.error(f"Provider agent error: {e}")
        return ProviderResponse(
            action="provide_info",
            message="Technical difficulties, please wait.",
            final=False
        )
```

---

### Step-by-Step: orchestrator.py

**Purpose**: Coordinate all negotiations in parallel.

```python
# ============================================================
# FILE: src/orchestrator.py
# PURPOSE: Coordinate parallel negotiations with session management
# ============================================================

"""Orchestrator - coordinates parallel negotiations with session management."""
import asyncio
import secrets
from datetime import datetime, timedelta
from typing import AsyncGenerator
from .models import (
    NegotiationRequest, NegotiationSession, ProviderNegotiation,
    NegotiationMessage, NegotiationUpdate
)
from .providers import generate_provider, get_provider_response
from .negotiator import negotiate_turn, create_opening
from .config import get_settings, logger

# Thread-safe session storage
_sessions: dict[str, tuple[NegotiationSession, datetime]] = {}
_lock = asyncio.Lock()


async def cleanup_expired() -> None:
    """Remove sessions older than TTL."""
    settings = get_settings()
    async with _lock:
        now = datetime.now()
        expired = [
            sid for sid, (_, created) in _sessions.items()
            if now - created > timedelta(seconds=settings.session_ttl_seconds)
        ]
        for sid in expired:
            del _sessions[sid]
            logger.info(f"Cleaned up expired session: {sid}")


async def create_session(request: NegotiationRequest) -> NegotiationSession:
    """Create new negotiation session."""
    await cleanup_expired()

    # Secure 128-bit session ID
    session_id = secrets.token_urlsafe(16)

    # Base price for provider generation
    base_price = (request.target_price + request.max_price) / 2

    # Generate providers with random personalities
    providers = []
    for i in range(request.num_providers):
        data = generate_provider(base_price, i)
        providers.append(ProviderNegotiation(
            provider_id=data["provider_id"],
            provider_name=data["provider_name"],
            personality=data["personality"],
            initial_price=data["initial_price"],
            current_price=data["initial_price"],
            min_price=data["min_price"],  # Internal only
        ))

    session = NegotiationSession(
        session_id=session_id,
        item_description=request.item_description,
        target_price=request.target_price,
        max_price=request.max_price,
        strategy=request.strategy,
        providers=providers,
        created_at=datetime.now().isoformat()
    )

    # Thread-safe storage
    async with _lock:
        _sessions[session_id] = (session, datetime.now())

    logger.info(f"Created session {session_id} with {len(providers)} providers")
    return session


async def get_session(session_id: str) -> NegotiationSession | None:
    """Get session by ID (thread-safe)."""
    async with _lock:
        item = _sessions.get(session_id)
        return item[0] if item else None


async def run_round(
    session: NegotiationSession,
    provider: ProviderNegotiation
) -> tuple[NegotiationUpdate, bool]:
    """Run single negotiation round with one provider.

    Returns: (update_event, is_finished)
    """
    try:
        # STEP 1: Get negotiator's action
        if provider.rounds == 0:
            # First round - create opening offer
            action = await create_opening(
                session.item_description,
                session.target_price,
                session.max_price,
                session.strategy,
                provider.provider_name,
                provider.initial_price
            )
        else:
            # Subsequent rounds - respond to provider
            last_msg = next(
                (m for m in reversed(provider.messages) if m.role == "provider"),
                None
            )
            action = await negotiate_turn(
                session.item_description,
                session.target_price,
                session.max_price,
                session.strategy,
                provider.provider_name,
                provider.current_price or provider.initial_price,
                [m.model_dump() for m in provider.messages],
                last_msg.message if last_msg else "",
                last_msg.amount if last_msg else None
            )

        # Record negotiator's message
        provider.messages.append(NegotiationMessage(
            role="negotiator",
            action=action.action,
            amount=action.amount,
            message=action.message,
            timestamp=datetime.now().isoformat()
        ))

        # STEP 2: Handle terminal actions from negotiator
        if action.action == "accept":
            provider.status = "accepted"
            return NegotiationUpdate(
                session_id=session.session_id,
                provider_id=provider.provider_id,
                event_type="deal_found",
                data={"status": "accepted", "price": provider.current_price, "msg": action.message}
            ), True

        if action.action == "walk_away":
            provider.status = "walked_away"
            return NegotiationUpdate(
                session_id=session.session_id,
                provider_id=provider.provider_id,
                event_type="status_change",
                data={"status": "walked_away", "msg": action.message}
            ), True

        # STEP 3: Get provider's response
        response = await get_provider_response(
            provider.personality,
            provider.initial_price,
            provider.min_price,
            provider.current_price or provider.initial_price,
            [m.model_dump() for m in provider.messages],
            action.message,
            action.amount
        )

        # Record provider's message
        provider.messages.append(NegotiationMessage(
            role="provider",
            action=response.action,
            amount=response.amount,
            message=response.message,
            timestamp=datetime.now().isoformat()
        ))

        # Update price if counter-offered
        if response.amount:
            provider.current_price = response.amount
        provider.rounds += 1

        # STEP 4: Handle provider responses
        if response.action == "accept":
            provider.status = "accepted"
            provider.current_price = action.amount
            return NegotiationUpdate(
                session_id=session.session_id,
                provider_id=provider.provider_id,
                event_type="deal_found",
                data={"status": "accepted", "price": action.amount, "msg": response.message}
            ), True

        if response.action == "reject":
            provider.status = "rejected"
            return NegotiationUpdate(
                session_id=session.session_id,
                provider_id=provider.provider_id,
                event_type="status_change",
                data={"status": "rejected", "msg": response.message}
            ), True

        # Negotiation continues
        return NegotiationUpdate(
            session_id=session.session_id,
            provider_id=provider.provider_id,
            event_type="message",
            data={
                "round": provider.rounds,
                "price": provider.current_price,
                "negotiator": action.model_dump(),
                "provider": response.model_dump()
            }
        ), False

    except Exception as e:
        logger.error(f"Round error for {provider.provider_id}: {e}")
        provider.status = "error"
        return NegotiationUpdate(
            session_id=session.session_id,
            provider_id=provider.provider_id,
            event_type="error",
            data={"status": "error", "msg": "Negotiation error"}
        ), True


async def run_negotiations(session_id: str) -> AsyncGenerator[NegotiationUpdate, None]:
    """Run all negotiations with real-time updates.

    This is an ASYNC GENERATOR - yields updates as they happen.
    The frontend receives these via Server-Sent Events (SSE).
    """
    settings = get_settings()
    session = await get_session(session_id)
    if not session:
        return

    for round_num in range(settings.max_rounds):
        # Send heartbeat (keeps connection alive)
        yield NegotiationUpdate(
            session_id=session_id,
            provider_id="system",
            event_type="heartbeat",
            data={"round": round_num + 1}
        )

        # Get active providers
        active = [p for p in session.providers if p.status == "negotiating"]
        if not active:
            break

        # RUN ALL NEGOTIATIONS IN PARALLEL
        tasks = [run_round(session, p) for p in active]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for provider, result in zip(active, results):
            if isinstance(result, Exception):
                logger.error(f"Task error: {result}")
                provider.status = "error"
                yield NegotiationUpdate(
                    session_id=session_id,
                    provider_id=provider.provider_id,
                    event_type="error",
                    data={"msg": "Task failed"}
                )
            else:
                update, _ = result
                yield update

        session.total_rounds = round_num + 1
        await asyncio.sleep(0.3)  # Small delay between rounds

    # Find best deal among accepted offers
    accepted = [p for p in session.providers if p.status == "accepted"]
    if accepted:
        session.best_deal = min(accepted, key=lambda p: p.current_price or float('inf'))

    session.status = "completed"

    # Final completion event
    yield NegotiationUpdate(
        session_id=session_id,
        provider_id="system",
        event_type="completed",
        data={
            "best": session.best_deal.provider_name if session.best_deal else None,
            "price": session.best_deal.current_price if session.best_deal else None,
            "deals": len(accepted),
            "total": len(session.providers)
        }
    )
```

**Key Concepts**:
- `asyncio.gather(*tasks)` → Run all providers IN PARALLEL
- `AsyncGenerator[NegotiationUpdate, None]` → Yield updates as they happen
- `async with _lock` → Thread-safe session access
- Heartbeat events → Keep SSE connection alive

---

### Step-by-Step: main.py

**Purpose**: FastAPI HTTP/SSE endpoints.

```python
# ============================================================
# FILE: src/main.py
# PURPOSE: FastAPI backend with SSE streaming
# ============================================================

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

# Simple in-memory rate limiting
_request_counts: dict[str, list[float]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifecycle - startup/shutdown hooks."""
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
    """Simple rate limiter - 60 requests/minute/IP."""
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
    """Rate limiting - only for POST requests."""
    ip = request.client.host if request.client else "unknown"
    if request.method == "POST" and request.url.path.startswith("/api/"):
        if not check_rate_limit(ip, limit=10, window=60):
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
    """Get session state (without exposing min_price)."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # SECURITY: Don't expose min_price to clients
    response = session.model_dump()
    for p in response["providers"]:
        p.pop("min_price", None)
    return response


@app.get("/api/negotiate/{session_id}/stream")
async def stream_negotiation(session_id: str):
    """Stream negotiation updates via SSE."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator():
        try:
            async for update in run_negotiations(session_id):
                yield {
                    "event": update.event_type,
                    "data": json.dumps(update.model_dump())
                }
        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for {session_id}")
        except Exception as e:
            logger.error(f"Stream error for {session_id}: {e}")
            yield {"event": "error", "data": json.dumps({"error": "Stream failed"})}

    return EventSourceResponse(
        event_generator(),
        ping=15,  # Send ping every 15s
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
```

---

## 3. Frontend Deep Dive

### File Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx       # Root layout
│   │   ├── page.tsx         # Main page component
│   │   └── error.tsx        # Error boundary
│   ├── components/
│   │   ├── NegotiationForm.tsx
│   │   ├── ProviderCard.tsx
│   │   └── ResultsSummary.tsx
│   ├── lib/
│   │   └── api.ts           # API client + SSE handling
│   └── types/
│       └── negotiation.ts   # TypeScript interfaces
├── package.json
├── tailwind.config.ts
└── next.config.ts
```

### Key File: api.ts (SSE Streaming)

```typescript
// ============================================================
// FILE: src/lib/api.ts
// PURPOSE: API client with SSE reconnection logic
// ============================================================

import { NegotiationRequest, NegotiationSession, NegotiationUpdate } from "@/types/negotiation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Start a new negotiation
export async function startNegotiation(request: NegotiationRequest): Promise<NegotiationSession> {
  const response = await fetch(`${API_URL}/api/negotiate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || "Failed to start negotiation");
  }
  return response.json();
}

// Get session state
export async function getSession(sessionId: string): Promise<NegotiationSession> {
  const response = await fetch(`${API_URL}/api/negotiate/${sessionId}`);
  if (!response.ok) throw new Error("Failed to get session");
  return response.json();
}

interface StreamCallbacks {
  onUpdate: (data: NegotiationUpdate) => void;
  onComplete: () => void;
  onError: (error: Error) => void;
}

// Stream negotiation with automatic reconnection
export function streamNegotiation(sessionId: string, callbacks: StreamCallbacks): () => void {
  let eventSource: EventSource | null = null;
  let retryCount = 0;
  const maxRetries = 3;
  const retryDelay = 2000;
  let closed = false;

  const connect = () => {
    if (closed) return;

    // Create SSE connection
    eventSource = new EventSource(`${API_URL}/api/negotiate/${sessionId}/stream`);

    eventSource.onopen = () => {
      retryCount = 0; // Reset on successful connection
    };

    // Handle named events
    const eventTypes = ["message", "status_change", "deal_found", "heartbeat", "error"];
    eventTypes.forEach((type) => {
      eventSource?.addEventListener(type, (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data) as NegotiationUpdate;
          callbacks.onUpdate(data);
        } catch {
          console.error(`Failed to parse ${type} event`);
        }
      });
    });

    // Handle completion
    eventSource.addEventListener("completed", (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data) as NegotiationUpdate;
        callbacks.onUpdate(data);
        callbacks.onComplete();
        cleanup();
      } catch {
        callbacks.onComplete();
        cleanup();
      }
    });

    // Handle ping (heartbeat)
    eventSource.addEventListener("ping", () => {
      // Connection alive
    });

    // Handle errors with reconnection
    eventSource.onerror = () => {
      if (closed) return;

      eventSource?.close();
      eventSource = null;

      if (retryCount < maxRetries) {
        retryCount++;
        console.log(`Connection lost. Retrying (${retryCount}/${maxRetries})...`);
        setTimeout(connect, retryDelay * retryCount); // Exponential backoff
      } else {
        callbacks.onError(new Error("Connection lost after multiple retries"));
      }
    };
  };

  const cleanup = () => {
    closed = true;
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  };

  connect();
  return cleanup; // Return cleanup function
}
```

---

## 4. Building It Yourself

### Step 1: Backend Setup

```bash
# Create project directory
mkdir negotiate-ai && cd negotiate-ai
mkdir backend && cd backend

# Initialize with uv
uv init
uv add fastapi uvicorn pydantic-ai pydantic-settings sse-starlette httpx python-dotenv

# Create structure
mkdir src tests
touch src/__init__.py src/config.py src/models.py src/negotiator.py
touch src/providers.py src/orchestrator.py src/main.py
touch tests/__init__.py tests/test_api.py

# Create .env
echo "OPENAI_API_KEY=sk-your-key-here" > .env

# Create run.py
cat > run.py << 'EOF'
import uvicorn
if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
EOF
```

### Step 2: Frontend Setup

```bash
cd .. && mkdir frontend && cd frontend

# Create Next.js app
npx create-next-app@latest . --typescript --tailwind --eslint --app --src-dir

# Create structure
mkdir -p src/components src/lib src/types

# Set API URL
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
```

### Step 3: Copy Code

Copy each file from this guide in order:
1. `backend/src/config.py`
2. `backend/src/models.py`
3. `backend/src/negotiator.py`
4. `backend/src/providers.py`
5. `backend/src/orchestrator.py`
6. `backend/src/main.py`
7. `frontend/src/types/negotiation.ts`
8. `frontend/src/lib/api.ts`
9. `frontend/src/app/page.tsx`
10. `frontend/src/components/*.tsx`

### Step 4: Run

```bash
# Terminal 1: Backend
cd backend && uv run python run.py

# Terminal 2: Frontend
cd frontend && npm run dev
```

Open http://localhost:3000

---

## 5. Key Concepts Explained

### What is Pydantic AI?

Pydantic AI is a framework for building AI agents with:
- **Structured Outputs**: Force LLM to return valid JSON matching your Pydantic model
- **Type Safety**: Full TypeScript-like typing in Python
- **Tool Calling**: Let agents call functions (not used here, but powerful)
- **Model Agnostic**: Works with OpenAI, Anthropic, Gemini, etc.

```python
# The magic line that forces structured output:
Agent('openai:gpt-4o', output_type=NegotiationAction)

# Now the LLM MUST return:
{
  "action": "counter",
  "amount": 2500.00,
  "message": "I can offer $2,500",
  "reasoning": "Meeting in the middle",
  "confidence": 0.8
}
```

### What is Server-Sent Events (SSE)?

SSE is a simple way to stream data from server to client:
- One-way (server → client)
- Built into browsers (`EventSource` API)
- Automatic reconnection
- Perfect for real-time updates

```python
# Backend yields events
yield {"event": "message", "data": json.dumps(update)}

# Frontend receives
eventSource.addEventListener("message", (e) => {
  const data = JSON.parse(e.data);
  // Update UI
});
```

### Why Parallel Negotiation?

In real-world scenarios (like Lanesurf), you want to:
1. Talk to multiple vendors simultaneously
2. Compare offers in real-time
3. Accept the best deal
4. Save time vs. sequential calls

```python
# The key line for parallelism:
tasks = [run_round(session, p) for p in active_providers]
results = await asyncio.gather(*tasks)  # All run at once!
```

### Agent vs Agent Communication

In this demo:
- **Negotiator Agent**: Works FOR you (GPT-4o-mini)
- **Provider Agents**: Simulate vendors (GPT-4o-mini)
- They communicate via structured JSON, not free-form text

In production (like Lanesurf):
- Agents would talk to REAL humans via phone/voice
- Same patterns apply: structured outputs, fallbacks, timeouts

---

## Next Steps

1. **Add Voice**: Integrate OpenAI TTS/Whisper for voice conversations
2. **Add Database**: Replace in-memory storage with PostgreSQL
3. **Add Authentication**: Protect endpoints with JWT
4. **Add Analytics**: Track negotiation success rates
5. **Add Fine-tuning**: Train models on successful negotiations

Good luck with your Lanesurf interview!
