"""Pydantic AI Negotiator Agent - the core AI that negotiates on your behalf."""
import asyncio
from pydantic_ai import Agent
from .models import NegotiationAction, NegotiationStrategy
from .config import get_settings, logger

_negotiator_agent: Agent[None, NegotiationAction] | None = None


def get_negotiator_agent() -> Agent[None, NegotiationAction]:
    """Lazy init negotiator agent."""
    global _negotiator_agent
    if _negotiator_agent is None:
        settings = get_settings()
        _negotiator_agent = Agent(
            f'openai:{settings.openai_model}',
            result_type=NegotiationAction,
            system_prompt="""Expert negotiator AI. Get the best price for your client.
STRATEGIES: AGGRESSIVE (low offers, walk away), BALANCED (fair deals), CONSERVATIVE (quick deals).
RULES: Never exceed max_price, aim below target, know when to close. Keep messages under 100 words."""
        )
    return _negotiator_agent


async def negotiate_turn(
    item: str, target: float, max_price: float, strategy: NegotiationStrategy,
    provider: str, current_price: float, history: list[dict],
    latest_msg: str, latest_offer: float | None
) -> NegotiationAction:
    """Execute one negotiation turn with timeout."""
    settings = get_settings()
    history_text = "\n".join([
        f"{'You' if m['role'] == 'negotiator' else 'Provider'}: {m['message']}"
        + (f" [${m['amount']}]" if m.get('amount') else "")
        for m in history[-6:]
    ])

    prompt = f"""Item: {item} | Target: ${target} | Max: ${max_price} | Strategy: {strategy.value.upper()}
Provider: {provider} | Current price: ${current_price}
History: {history_text or 'None'}
Latest: "{latest_msg}" {f'Offer: ${latest_offer}' if latest_offer else ''}
Your move?"""

    try:
        result = await asyncio.wait_for(
            get_negotiator_agent().run(prompt),
            timeout=settings.api_timeout
        )
        return result.output
    except asyncio.TimeoutError:
        logger.warning(f"Negotiator timeout for {provider}")
        return NegotiationAction(
            action="counter", amount=target, message="I need to think. My offer stands.",
            reasoning="Timeout fallback", confidence=0.3
        )
    except Exception as e:
        logger.error(f"Negotiator error: {e}")
        return NegotiationAction(
            action="ask_question", message="Could you clarify your position?",
            reasoning=f"Error recovery: {str(e)[:50]}", confidence=0.2
        )


async def create_opening(
    item: str, target: float, max_price: float, strategy: NegotiationStrategy,
    provider: str, asking_price: float
) -> NegotiationAction:
    """Create opening offer with timeout."""
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
        pct = {"aggressive": 0.65, "balanced": 0.8, "conservative": 0.88}[strategy.value]
        return NegotiationAction(
            action="offer", amount=round(asking_price * pct, 2),
            message=f"I'd like to offer ${round(asking_price * pct, 2)} for this.",
            reasoning="Timeout fallback", confidence=0.5
        )
    except Exception as e:
        logger.error(f"Opening offer error: {e}")
        return NegotiationAction(
            action="ask_question", message="Can you tell me more about your service?",
            reasoning=f"Error: {str(e)[:50]}", confidence=0.2
        )
