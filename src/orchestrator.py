"""Orchestrator - coordinates parallel negotiations across multiple providers."""
import asyncio
import uuid
from datetime import datetime
from typing import AsyncGenerator
from .models import (
    NegotiationRequest, NegotiationSession, ProviderNegotiation,
    NegotiationMessage, NegotiationUpdate, NegotiationStrategy
)
from .providers import generate_provider, get_provider_response
from .negotiator import negotiate_turn, create_opening_offer

# In-memory session storage (would use Redis/DB in production)
sessions: dict[str, NegotiationSession] = {}


async def create_session(request: NegotiationRequest) -> NegotiationSession:
    """Create a new negotiation session with multiple providers."""
    session_id = str(uuid.uuid4())[:8]

    # Generate providers with different personalities
    base_price = (request.target_price + request.max_price) / 2
    providers = []

    for i in range(request.num_providers):
        provider_data = generate_provider(request.item_description, base_price, i)
        provider = ProviderNegotiation(
            provider_id=provider_data["provider_id"],
            provider_name=provider_data["provider_name"],
            personality=provider_data["personality"],
            initial_price=provider_data["initial_price"],
            current_price=provider_data["initial_price"],
            status="negotiating",
            messages=[],
            rounds=0
        )
        # Store min_price separately (internal)
        provider._min_price = provider_data["min_price"]
        providers.append(provider)

    session = NegotiationSession(
        session_id=session_id,
        item_description=request.item_description,
        target_price=request.target_price,
        max_price=request.max_price,
        strategy=request.strategy,
        providers=providers,
        status="in_progress"
    )

    sessions[session_id] = session
    return session


async def run_negotiation_round(
    session: NegotiationSession,
    provider: ProviderNegotiation,
    provider_min_price: float
) -> tuple[NegotiationUpdate, bool]:
    """Run a single round of negotiation with one provider."""

    # Check if first round
    if provider.rounds == 0:
        # Opening offer from our negotiator
        action = await create_opening_offer(
            item_description=session.item_description,
            target_price=session.target_price,
            max_price=session.max_price,
            strategy=session.strategy,
            provider_name=provider.provider_name,
            provider_initial_price=provider.initial_price
        )
    else:
        # Get the provider's last message
        provider_messages = [m for m in provider.messages if m.role == "provider"]
        last_provider_msg = provider_messages[-1] if provider_messages else None

        action = await negotiate_turn(
            item_description=session.item_description,
            target_price=session.target_price,
            max_price=session.max_price,
            strategy=session.strategy,
            provider_name=provider.provider_name,
            provider_current_price=provider.current_price or provider.initial_price,
            conversation_history=[m.model_dump() for m in provider.messages],
            provider_latest_message=last_provider_msg.message if last_provider_msg else "",
            provider_latest_offer=last_provider_msg.amount if last_provider_msg else None
        )

    # Record our action
    timestamp = datetime.now().isoformat()
    provider.messages.append(NegotiationMessage(
        role="negotiator",
        action=action.action,
        amount=action.amount,
        message=action.message,
        timestamp=timestamp
    ))

    # Check for terminal actions
    if action.action == "accept":
        provider.status = "accepted"
        return NegotiationUpdate(
            session_id=session.session_id,
            provider_id=provider.provider_id,
            event_type="status_change",
            data={
                "status": "accepted",
                "final_price": provider.current_price,
                "message": action.message
            }
        ), True

    if action.action == "walk_away":
        provider.status = "walked_away"
        return NegotiationUpdate(
            session_id=session.session_id,
            provider_id=provider.provider_id,
            event_type="status_change",
            data={"status": "walked_away", "message": action.message}
        ), True

    # Get provider response
    provider_response = await get_provider_response(
        personality=provider.personality,
        initial_price=provider.initial_price,
        min_price=provider_min_price,
        current_price=provider.current_price or provider.initial_price,
        conversation_history=[m.model_dump() for m in provider.messages],
        customer_message=action.message,
        customer_offer=action.amount
    )

    # Record provider response
    provider.messages.append(NegotiationMessage(
        role="provider",
        action=provider_response.action,
        amount=provider_response.amount,
        message=provider_response.message,
        timestamp=datetime.now().isoformat()
    ))

    # Update current price if provider made an offer
    if provider_response.amount:
        provider.current_price = provider_response.amount

    provider.rounds += 1

    # Check if provider accepted or rejected
    if provider_response.action == "accept":
        provider.status = "accepted"
        provider.current_price = action.amount  # They accepted our offer
        return NegotiationUpdate(
            session_id=session.session_id,
            provider_id=provider.provider_id,
            event_type="deal_found",
            data={
                "status": "accepted",
                "final_price": action.amount,
                "provider_message": provider_response.message
            }
        ), True

    if provider_response.action == "reject":
        provider.status = "rejected"
        return NegotiationUpdate(
            session_id=session.session_id,
            provider_id=provider.provider_id,
            event_type="status_change",
            data={"status": "rejected", "message": provider_response.message}
        ), True

    # Negotiation continues
    return NegotiationUpdate(
        session_id=session.session_id,
        provider_id=provider.provider_id,
        event_type="message",
        data={
            "negotiator_action": action.model_dump(),
            "provider_response": provider_response.model_dump(),
            "round": provider.rounds
        }
    ), False


async def run_parallel_negotiations(
    session_id: str,
    max_rounds: int = 5
) -> AsyncGenerator[NegotiationUpdate, None]:
    """Run negotiations with all providers in parallel, yielding updates."""

    session = sessions.get(session_id)
    if not session:
        return

    # Store min prices separately
    min_prices = {}
    for p in session.providers:
        min_prices[p.provider_id] = getattr(p, '_min_price', p.initial_price * 0.7)

    for round_num in range(max_rounds):
        # Get providers still negotiating
        active_providers = [p for p in session.providers if p.status == "negotiating"]

        if not active_providers:
            break

        # Run all negotiations in parallel
        tasks = []
        for provider in active_providers:
            task = run_negotiation_round(session, provider, min_prices[provider.provider_id])
            tasks.append((provider.provider_id, task))

        # Gather results
        results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)

        for (provider_id, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                yield NegotiationUpdate(
                    session_id=session_id,
                    provider_id=provider_id,
                    event_type="status_change",
                    data={"status": "error", "message": str(result)}
                )
            else:
                update, is_complete = result
                yield update

        session.total_rounds = round_num + 1

        # Small delay between rounds
        await asyncio.sleep(0.5)

    # Find best deal
    accepted = [p for p in session.providers if p.status == "accepted"]
    if accepted:
        best = min(accepted, key=lambda p: p.current_price or float('inf'))
        session.best_deal = best
        yield NegotiationUpdate(
            session_id=session_id,
            provider_id=best.provider_id,
            event_type="completed",
            data={
                "best_provider": best.provider_name,
                "best_price": best.current_price,
                "total_providers": len(session.providers),
                "deals_found": len(accepted)
            }
        )

    session.status = "completed"


def get_session(session_id: str) -> NegotiationSession | None:
    """Get a session by ID."""
    return sessions.get(session_id)
