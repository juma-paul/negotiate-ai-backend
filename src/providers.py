"""Simulated providers with different negotiation personalities."""
import random
import asyncio
from pydantic_ai import Agent
from .models import ProviderPersonality, ProviderResponse
from .config import get_settings, logger

PROVIDER_NAMES = [
    "QuickShip Logistics", "FastFreight Co", "Budget Haulers Inc",
    "Premium Transport", "Lightning Delivery", "Steady Eddie Trucking",
    "CrossCountry Carriers", "Reliable Routes LLC", "Express Lane Shipping", "ValueMove Transport"
]

_provider_agent: Agent[None, ProviderResponse] | None = None


def get_provider_agent() -> Agent[None, ProviderResponse]:
    """Lazy init provider agent."""
    global _provider_agent
    if _provider_agent is None:
        settings = get_settings()
        _provider_agent = Agent(
            f'openai:{settings.openai_model_mini}',
            output_type=ProviderResponse,  # Changed from result_type
            system_prompt="""You simulate a service provider in a negotiation.
Respond according to personality: FIRM (5-10% discount max), FLEXIBLE (15-25% off),
DESPERATE (30-40% off, accept quickly), PREMIUM (justify high prices, small discounts).
Set 'final'=true for absolute final offer. Keep messages under 100 words."""
        )
    return _provider_agent


def generate_provider(base_price: float, index: int) -> dict:
    """Generate provider with personality and pricing."""
    personality = random.choice(list(ProviderPersonality))
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
        "min_price": round(min_price, 2),
    }


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
