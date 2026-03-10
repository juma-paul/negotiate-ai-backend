"""Provider AI agent for simulating trucking company responses."""
import asyncio
from pydantic_ai import Agent
from .models import ProviderPersonality, ProviderResponse
from .config import get_settings, logger

_provider_agent: Agent[None, ProviderResponse] | None = None


def get_provider_agent() -> Agent[None, ProviderResponse]:
    """Lazy init provider agent."""
    global _provider_agent
    if _provider_agent is None:
        settings = get_settings()
        _provider_agent = Agent(
            f'openai:{settings.openai_model_mini}',
            output_type=ProviderResponse,
            system_prompt="""You simulate a trucking company dispatcher in a freight rate negotiation.
Respond according to personality:
- FIRM: Hard negotiator, 5-10% discount max, stands ground
- FLEXIBLE: Reasonable, willing to negotiate 15-25% off for good customers
- DESPERATE: Needs business badly, accept quickly, 30-40% off possible
- PREMIUM: Luxury service, justify high prices, small discounts only

Set 'final'=true for your absolute final offer. Keep messages under 100 words.
Be realistic - you're a trucking company, talk about capacity, routes, fuel costs."""
        )
    return _provider_agent


async def get_provider_response(
    personality: ProviderPersonality,
    initial_price: float,
    min_price: float,
    current_price: float,
    history: list[dict],
    customer_message: str,
    customer_offer: float | None
) -> ProviderResponse:
    """Get response from simulated provider with timeout."""
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
        return ProviderResponse(action="counter", amount=current_price * 0.95,
                               message="Let me think about that... how about this price?", final=False)
    except Exception as e:
        logger.error(f"Provider agent error: {e}")
        return ProviderResponse(action="provide_info", message="Technical difficulties, please wait.", final=False)
