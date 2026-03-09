"""Simulated providers with different negotiation personalities."""
import random
from pydantic_ai import Agent
from .models import ProviderPersonality, ProviderResponse

# Lazy initialization of the agent
_provider_agent = None

def get_provider_agent():
    global _provider_agent
    if _provider_agent is None:
        _provider_agent = Agent(
            'openai:gpt-4o-mini',
            result_type=ProviderResponse,
            system_prompt="""You are simulating a service provider in a negotiation.

You will receive:
1. Your personality type (firm, flexible, desperate, premium)
2. Your minimum acceptable price
3. Your initial asking price
4. The negotiation history
5. The customer's latest message/offer

Respond according to your personality:
- FIRM: Rarely lower your price more than 5-10%. Stand your ground.
- FLEXIBLE: Willing to negotiate, can go 15-25% lower if pushed.
- DESPERATE: Need the business, can go 30-40% lower, accept quickly.
- PREMIUM: Justify your higher prices with quality, small discounts only.

Always respond with a realistic message a real vendor would say.
Set 'final' to true if this is your absolute final offer."""
        )
    return _provider_agent


# Funny/realistic provider names
PROVIDER_NAMES = [
    "QuickShip Logistics",
    "FastFreight Co",
    "Budget Haulers Inc",
    "Premium Transport Services",
    "Lightning Delivery",
    "Steady Eddie Trucking",
    "CrossCountry Carriers",
    "Reliable Routes LLC",
    "Express Lane Shipping",
    "ValueMove Transport"
]


def generate_provider(item_description: str, base_price: float, index: int) -> dict:
    """Generate a simulated provider with personality and pricing."""
    personality = random.choice(list(ProviderPersonality))

    # Adjust initial price based on personality
    price_multipliers = {
        ProviderPersonality.FIRM: random.uniform(1.1, 1.3),
        ProviderPersonality.FLEXIBLE: random.uniform(1.0, 1.2),
        ProviderPersonality.DESPERATE: random.uniform(0.9, 1.1),
        ProviderPersonality.PREMIUM: random.uniform(1.2, 1.5),
    }

    # Minimum acceptable price based on personality
    min_price_multipliers = {
        ProviderPersonality.FIRM: random.uniform(0.9, 0.95),
        ProviderPersonality.FLEXIBLE: random.uniform(0.75, 0.85),
        ProviderPersonality.DESPERATE: random.uniform(0.6, 0.7),
        ProviderPersonality.PREMIUM: random.uniform(0.85, 0.95),
    }

    initial_price = base_price * price_multipliers[personality]
    min_price = base_price * min_price_multipliers[personality]

    return {
        "provider_id": f"provider_{index}",
        "provider_name": PROVIDER_NAMES[index % len(PROVIDER_NAMES)],
        "personality": personality,
        "initial_price": round(initial_price, 2),
        "min_price": round(min_price, 2),  # Internal, not shared
        "current_price": round(initial_price, 2),
    }


async def get_provider_response(
    personality: ProviderPersonality,
    initial_price: float,
    min_price: float,
    current_price: float,
    conversation_history: list[dict],
    customer_message: str,
    customer_offer: float | None
) -> ProviderResponse:
    """Get a response from the simulated provider."""

    history_text = "\n".join([
        f"{'Customer' if m['role'] == 'negotiator' else 'You'}: {m['message']}"
        for m in conversation_history[-6:]  # Last 6 messages for context
    ])

    prompt = f"""
Personality: {personality.value.upper()}
Your initial asking price: ${initial_price}
Your minimum acceptable price: ${min_price}
Your current offered price: ${current_price}

Conversation history:
{history_text}

Customer's latest message: {customer_message}
Customer's offer: ${customer_offer if customer_offer else 'No specific offer'}

Respond as this provider. If the customer's offer is at or above your minimum, you can accept.
If they're close, make a counter-offer. If they're way below, stand firm or reject.
"""

    result = await get_provider_agent().run(prompt)
    return result.output
