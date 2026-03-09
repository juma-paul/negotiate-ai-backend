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

# Thread-safe session storage with TTL
_sessions: dict[str, tuple[NegotiationSession, datetime]] = {}
_lock = asyncio.Lock()


async def cleanup_expired() -> None:
    """Remove expired sessions."""
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
    """Create new negotiation session with secure ID."""
    await cleanup_expired()
    session_id = secrets.token_urlsafe(16)  # Secure 128-bit ID
    base_price = (request.target_price + request.max_price) / 2

    providers = []
    for i in range(request.num_providers):
        data = generate_provider(base_price, i)
        providers.append(ProviderNegotiation(
            provider_id=data["provider_id"],
            provider_name=data["provider_name"],
            personality=data["personality"],
            initial_price=data["initial_price"],
            current_price=data["initial_price"],
            min_price=data["min_price"],
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

    async with _lock:
        _sessions[session_id] = (session, datetime.now())
    logger.info(f"Created session {session_id} with {len(providers)} providers")
    return session


async def get_session(session_id: str) -> NegotiationSession | None:
    """Get session by ID (thread-safe)."""
    async with _lock:
        item = _sessions.get(session_id)
        return item[0] if item else None


async def run_round(session: NegotiationSession, provider: ProviderNegotiation) -> tuple[NegotiationUpdate, bool]:
    """Run single negotiation round with one provider."""
    try:
        # Get negotiator action
        if provider.rounds == 0:
            action = await create_opening(
                session.item_description, session.target_price, session.max_price,
                session.strategy, provider.provider_name, provider.initial_price
            )
        else:
            last_msg = next((m for m in reversed(provider.messages) if m.role == "provider"), None)
            action = await negotiate_turn(
                session.item_description, session.target_price, session.max_price,
                session.strategy, provider.provider_name,
                provider.current_price or provider.initial_price,
                [m.model_dump() for m in provider.messages],
                last_msg.message if last_msg else "",
                last_msg.amount if last_msg else None
            )

        # Record negotiator message
        provider.messages.append(NegotiationMessage(
            role="negotiator", action=action.action,
            amount=action.amount, message=action.message,
            timestamp=datetime.now().isoformat()
        ))

        # Handle terminal actions
        if action.action == "accept":
            provider.status = "accepted"
            return NegotiationUpdate(
                session_id=session.session_id, provider_id=provider.provider_id,
                event_type="deal_found",
                data={"status": "accepted", "price": provider.current_price, "msg": action.message}
            ), True

        if action.action == "walk_away":
            provider.status = "walked_away"
            return NegotiationUpdate(
                session_id=session.session_id, provider_id=provider.provider_id,
                event_type="status_change", data={"status": "walked_away", "msg": action.message}
            ), True

        # Get provider response
        response = await get_provider_response(
            provider.personality, provider.initial_price, provider.min_price,
            provider.current_price or provider.initial_price,
            [m.model_dump() for m in provider.messages],
            action.message, action.amount
        )

        provider.messages.append(NegotiationMessage(
            role="provider", action=response.action,
            amount=response.amount, message=response.message,
            timestamp=datetime.now().isoformat()
        ))

        if response.amount:
            provider.current_price = response.amount
        provider.rounds += 1

        if response.action == "accept":
            provider.status = "accepted"
            provider.current_price = action.amount
            return NegotiationUpdate(
                session_id=session.session_id, provider_id=provider.provider_id,
                event_type="deal_found",
                data={"status": "accepted", "price": action.amount, "msg": response.message}
            ), True

        if response.action == "reject":
            provider.status = "rejected"
            return NegotiationUpdate(
                session_id=session.session_id, provider_id=provider.provider_id,
                event_type="status_change", data={"status": "rejected", "msg": response.message}
            ), True

        return NegotiationUpdate(
            session_id=session.session_id, provider_id=provider.provider_id,
            event_type="message",
            data={"round": provider.rounds, "price": provider.current_price,
                  "negotiator": action.model_dump(), "provider": response.model_dump()}
        ), False

    except Exception as e:
        logger.error(f"Round error for {provider.provider_id}: {e}")
        provider.status = "error"
        return NegotiationUpdate(
            session_id=session.session_id, provider_id=provider.provider_id,
            event_type="error", data={"status": "error", "msg": "Negotiation error"}
        ), True


async def run_negotiations(session_id: str) -> AsyncGenerator[NegotiationUpdate, None]:
    """Run all negotiations with heartbeat."""
    settings = get_settings()
    session = await get_session(session_id)
    if not session:
        return

    for round_num in range(settings.max_rounds):
        # Send heartbeat
        yield NegotiationUpdate(
            session_id=session_id, provider_id="system",
            event_type="heartbeat", data={"round": round_num + 1}
        )

        active = [p for p in session.providers if p.status == "negotiating"]
        if not active:
            break

        # Run rounds in parallel
        tasks = [run_round(session, p) for p in active]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for provider, result in zip(active, results):
            if isinstance(result, Exception):
                logger.error(f"Task error: {result}")
                provider.status = "error"
                yield NegotiationUpdate(
                    session_id=session_id, provider_id=provider.provider_id,
                    event_type="error", data={"msg": "Task failed"}
                )
            else:
                update, _ = result
                yield update

        session.total_rounds = round_num + 1
        await asyncio.sleep(0.3)

    # Find best deal
    accepted = [p for p in session.providers if p.status == "accepted"]
    if accepted:
        session.best_deal = min(accepted, key=lambda p: p.current_price or float('inf'))

    session.status = "completed"
    yield NegotiationUpdate(
        session_id=session_id, provider_id="system",
        event_type="completed",
        data={
            "best": session.best_deal.provider_name if session.best_deal else None,
            "price": session.best_deal.current_price if session.best_deal else None,
            "deals": len(accepted), "total": len(session.providers)
        }
    )
