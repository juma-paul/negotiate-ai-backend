"""Pydantic models for the negotiation system."""
from typing import Literal
from pydantic import BaseModel, Field
from enum import Enum


class NegotiationStrategy(str, Enum):
    AGGRESSIVE = "aggressive"
    BALANCED = "balanced"
    CONSERVATIVE = "conservative"


class ProviderPersonality(str, Enum):
    FIRM = "firm"           # Rarely budges, high initial prices
    FLEXIBLE = "flexible"   # Willing to negotiate
    DESPERATE = "desperate" # Needs the business, will go low
    PREMIUM = "premium"     # High quality, justifies higher prices


class NegotiationRequest(BaseModel):
    """Request to start a new negotiation session."""
    item_description: str = Field(..., description="What you're negotiating for")
    target_price: float = Field(..., description="Your ideal price")
    max_price: float = Field(..., description="Maximum you're willing to pay")
    num_providers: int = Field(default=5, ge=1, le=10, description="Number of providers to negotiate with")
    strategy: NegotiationStrategy = Field(default=NegotiationStrategy.BALANCED)


class NegotiationAction(BaseModel):
    """Structured output from the negotiator agent."""
    action: Literal["offer", "counter", "accept", "reject", "ask_question", "walk_away"]
    amount: float | None = Field(default=None, description="Price amount if applicable")
    message: str = Field(..., description="Message to send to the provider")
    reasoning: str = Field(..., description="Internal reasoning for this action")
    confidence: float = Field(default=0.5, ge=0, le=1, description="Confidence in this action")


class ProviderResponse(BaseModel):
    """Response from a simulated provider."""
    action: Literal["offer", "counter", "accept", "reject", "provide_info"]
    amount: float | None = None
    message: str
    final: bool = False  # If true, this is their final offer


class NegotiationMessage(BaseModel):
    """A single message in the negotiation conversation."""
    role: Literal["negotiator", "provider"]
    action: str
    amount: float | None
    message: str
    timestamp: str


class ProviderNegotiation(BaseModel):
    """State of negotiation with a single provider."""
    provider_id: str
    provider_name: str
    personality: ProviderPersonality
    initial_price: float
    current_price: float | None = None
    status: Literal["negotiating", "accepted", "rejected", "walked_away"] = "negotiating"
    messages: list[NegotiationMessage] = []
    rounds: int = 0


class NegotiationSession(BaseModel):
    """Overall negotiation session state."""
    session_id: str
    item_description: str
    target_price: float
    max_price: float
    strategy: NegotiationStrategy
    providers: list[ProviderNegotiation] = []
    status: Literal["in_progress", "completed", "cancelled"] = "in_progress"
    best_deal: ProviderNegotiation | None = None
    total_rounds: int = 0


class NegotiationUpdate(BaseModel):
    """Real-time update sent to frontend."""
    session_id: str
    provider_id: str
    event_type: Literal["message", "status_change", "deal_found", "completed"]
    data: dict
