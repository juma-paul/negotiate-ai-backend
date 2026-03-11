"""Orchestrator - coordinates parallel negotiations with database persistence."""
import asyncio
from datetime import datetime
from typing import AsyncGenerator
from .models import (
    NegotiationRequest, NegotiationSession, ProviderNegotiation,
    NegotiationMessage, NegotiationUpdate
)
from .providers import get_provider_response
from .negotiator import negotiate_turn, create_opening
from .config import get_settings, logger
from .repositories import CompanyRepo, SessionRepo

# In-memory cache for active sessions (to avoid DB reads during negotiation)
_active_sessions: dict[str, NegotiationSession] = {}
_lock = asyncio.Lock()


async def create_session(request: NegotiationRequest, user_id: str | None = None) -> NegotiationSession:
    """Create new negotiation session with database persistence."""
    base_price = (request.target_price + request.max_price) / 2

    # Get random providers from database
    providers = await CompanyRepo.get_random_providers(request.num_providers, base_price)

    if not providers:
        raise ValueError("No providers available")

    # Create session in database
    session = await SessionRepo.create(
        user_id=user_id,
        item_description=request.item_description,
        target_price=request.target_price,
        max_price=request.max_price,
        strategy=request.strategy,
        providers=providers
    )

    # Cache for active negotiation
    async with _lock:
        _active_sessions[session.session_id] = session

    logger.info(f"Created session {session.session_id} with {len(providers)} providers")
    return session


async def get_session(session_id: str) -> NegotiationSession | None:
    """Get session by ID - check cache first, then database."""
    # Check cache first (for active negotiations)
    async with _lock:
        if session_id in _active_sessions:
            return _active_sessions[session_id]

    # Fall back to database
    session = await SessionRepo.get(session_id)
    if session and session.status == "in_progress":
        # Cache active sessions
        async with _lock:
            _active_sessions[session_id] = session
    return session


async def cancel_session(session_id: str) -> bool:
    """Cancel a session."""
    # Remove from cache
    async with _lock:
        _active_sessions.pop(session_id, None)

    # Update in database
    await SessionRepo.cancel_session(session_id)
    logger.info(f"Session {session_id} cancelled")
    return True


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

        # Record negotiator message (in-memory)
        provider.messages.append(NegotiationMessage(
            role="negotiator", action=action.action,
            amount=action.amount, message=action.message,
            timestamp=datetime.now().isoformat()
        ))

        # Persist to database
        await SessionRepo.add_message(
            session.session_id, provider.provider_id,
            "negotiator", action.action, action.amount, action.message
        )

        # Handle terminal actions
        if action.action == "accept":
            provider.status = "accepted"
            await SessionRepo.update_provider(
                session.session_id, provider.provider_id,
                status="accepted", rounds=provider.rounds
            )
            return NegotiationUpdate(
                session_id=session.session_id, provider_id=provider.provider_id,
                event_type="deal_found",
                data={"status": "accepted", "price": provider.current_price, "msg": action.message}
            ), True

        if action.action == "walk_away":
            provider.status = "walked_away"
            await SessionRepo.update_provider(
                session.session_id, provider.provider_id,
                status="walked_away", rounds=provider.rounds
            )
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

        # Persist provider message
        await SessionRepo.add_message(
            session.session_id, provider.provider_id,
            "provider", response.action, response.amount, response.message
        )

        if response.amount:
            provider.current_price = response.amount
        provider.rounds += 1

        # Update provider in database
        await SessionRepo.update_provider(
            session.session_id, provider.provider_id,
            current_price=provider.current_price, rounds=provider.rounds
        )

        if response.action == "accept":
            provider.status = "accepted"
            provider.current_price = action.amount
            await SessionRepo.update_provider(
                session.session_id, provider.provider_id,
                current_price=action.amount, status="accepted"
            )
            return NegotiationUpdate(
                session_id=session.session_id, provider_id=provider.provider_id,
                event_type="deal_found",
                data={"status": "accepted", "price": action.amount, "msg": response.message}
            ), True

        if response.action == "reject":
            provider.status = "rejected"
            await SessionRepo.update_provider(
                session.session_id, provider.provider_id,
                status="rejected"
            )
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
        await SessionRepo.update_provider(
            session.session_id, provider.provider_id, status="error"
        )
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

    # Persist completion to database
    await SessionRepo.complete_session(
        session_id,
        best_deal_company_id=session.best_deal.provider_id if session.best_deal else None,
        best_deal_price=session.best_deal.current_price if session.best_deal else None,
        total_rounds=session.total_rounds
    )

    # Save results for analytics (for each accepted deal)
    for provider in accepted:
        await SessionRepo.save_result(
            user_id=session.user_id,  # Use user_id from session
            session_id=session_id,
            company_id=provider.provider_id,
            initial_price=provider.initial_price,
            final_price=provider.current_price or provider.initial_price,
            strategy=session.strategy.value,
            rounds_taken=provider.rounds
        )

    # Remove from active cache
    async with _lock:
        _active_sessions.pop(session_id, None)

    yield NegotiationUpdate(
        session_id=session_id, provider_id="system",
        event_type="completed",
        data={
            "best": session.best_deal.provider_name if session.best_deal else None,
            "price": session.best_deal.current_price if session.best_deal else None,
            "deals": len(accepted), "total": len(session.providers)
        }
    )
