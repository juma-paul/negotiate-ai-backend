"""Pydantic models for the negotiation system - compact and validated."""
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from enum import Enum
import re


class NegotiationStrategy(str, Enum):
    AGGRESSIVE = "aggressive"
    BALANCED = "balanced"
    CONSERVATIVE = "conservative"


class ProviderPersonality(str, Enum):
    FIRM = "firm"
    FLEXIBLE = "flexible"
    DESPERATE = "desperate"
    PREMIUM = "premium"


class NegotiationRequest(BaseModel):
    """Request to start a negotiation - validated."""
    item_description: str = Field(..., min_length=5, max_length=500)
    target_price: float = Field(..., gt=0, le=1_000_000)
    max_price: float = Field(..., gt=0, le=1_000_000)
    num_providers: int = Field(default=5, ge=1, le=10)
    strategy: NegotiationStrategy = Field(default=NegotiationStrategy.BALANCED)

    @field_validator("item_description")
    @classmethod
    def sanitize_description(cls, v: str) -> str:
        """Remove potential prompt injection patterns."""
        dangerous = ["ignore previous", "disregard", "new instructions", "system:"]
        lower = v.lower()
        for pattern in dangerous:
            if pattern in lower:
                raise ValueError(f"Invalid content in description")
        return re.sub(r"[<>{}]", "", v)[:500]

    @field_validator("max_price")
    @classmethod
    def max_gte_target(cls, v: float, info) -> float:
        if "target_price" in info.data and v < info.data["target_price"]:
            raise ValueError("max_price must be >= target_price")
        return v


class NegotiationAction(BaseModel):
    """Structured output from negotiator agent."""
    action: Literal["offer", "counter", "accept", "reject", "ask_question", "walk_away"]
    amount: float | None = Field(default=None, ge=0, le=1_000_000)
    message: str = Field(..., max_length=500)
    reasoning: str = Field(..., max_length=500)
    confidence: float = Field(default=0.5, ge=0, le=1)


class ProviderResponse(BaseModel):
    """Response from simulated provider."""
    action: Literal["offer", "counter", "accept", "reject", "provide_info"]
    amount: float | None = Field(default=None, ge=0, le=1_000_000)
    message: str = Field(..., max_length=500)
    final: bool = False


class NegotiationMessage(BaseModel):
    """Single message in conversation."""
    role: Literal["negotiator", "provider"]
    action: str
    amount: float | None
    message: str
    timestamp: str


class ProviderNegotiation(BaseModel):
    """State of negotiation with one provider."""
    provider_id: str
    provider_name: str
    personality: ProviderPersonality
    initial_price: float
    current_price: float | None = None
    min_price: float = 0  # Internal, not exposed to client
    status: Literal["negotiating", "accepted", "rejected", "walked_away", "error"] = "negotiating"
    messages: list[NegotiationMessage] = []
    rounds: int = 0


class NegotiationSession(BaseModel):
    """Overall session state."""
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
    """Real-time update for SSE."""
    session_id: str
    provider_id: str
    event_type: Literal["message", "status_change", "deal_found", "completed", "heartbeat", "error"]
    data: dict
