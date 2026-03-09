"""Pydantic AI Negotiator Agent - the core AI that negotiates on your behalf."""
from pydantic_ai import Agent
from .models import NegotiationAction, NegotiationStrategy

# Lazy initialization
_negotiator_agent = None

def get_negotiator_agent():
    global _negotiator_agent
    if _negotiator_agent is None:
        _negotiator_agent = Agent(
            'openai:gpt-4o',
            result_type=NegotiationAction,
            system_prompt="""You are an expert negotiator AI agent. Your job is to get the best possible price for your client.

You will receive:
1. What the client wants to purchase/book
2. Their target price (ideal)
3. Their maximum price (absolute limit)
4. Your negotiation strategy
5. The conversation history with the provider
6. The provider's latest response

STRATEGIES:
- AGGRESSIVE: Push hard for the lowest price. Make low offers, be willing to walk away.
- BALANCED: Aim for fair deals. Counter reasonably, build rapport.
- CONSERVATIVE: Prioritize getting a deal done. Accept reasonable offers quickly.

RULES:
1. NEVER exceed the client's maximum price
2. Always try to get below the target price if possible
3. Use psychological tactics: anchoring, silence, walking away
4. Read the provider's signals - are they desperate? Firm?
5. Know when to close the deal vs push further

Your response must include:
- action: what to do (offer, counter, accept, reject, ask_question, walk_away)
- amount: the price you're proposing (if applicable)
- message: what to say to the provider
- reasoning: your internal thought process (for logging)
- confidence: how confident you are this is the right move (0-1)"""
        )
    return _negotiator_agent


async def negotiate_turn(
    item_description: str,
    target_price: float,
    max_price: float,
    strategy: NegotiationStrategy,
    provider_name: str,
    provider_current_price: float,
    conversation_history: list[dict],
    provider_latest_message: str,
    provider_latest_offer: float | None
) -> NegotiationAction:
    """Execute one turn of negotiation."""

    history_text = "\n".join([
        f"{'You' if m['role'] == 'negotiator' else 'Provider'}: {m['message']} " +
        (f"[${m['amount']}]" if m.get('amount') else "")
        for m in conversation_history[-8:]
    ])

    prompt = f"""
NEGOTIATION CONTEXT:
- Item: {item_description}
- Your target price: ${target_price}
- Your maximum price: ${max_price}
- Strategy: {strategy.value.upper()}
- Provider: {provider_name}
- Provider's current price: ${provider_current_price}

CONVERSATION HISTORY:
{history_text if history_text else "No previous messages - this is the start of negotiation."}

PROVIDER'S LATEST RESPONSE:
"{provider_latest_message}"
{f"Provider's offer: ${provider_latest_offer}" if provider_latest_offer else ""}

What is your next move? Remember your strategy is {strategy.value.upper()}.
"""

    result = await get_negotiator_agent().run(prompt)
    return result.output


async def create_opening_offer(
    item_description: str,
    target_price: float,
    max_price: float,
    strategy: NegotiationStrategy,
    provider_name: str,
    provider_initial_price: float
) -> NegotiationAction:
    """Create the opening offer to a provider."""

    prompt = f"""
NEW NEGOTIATION STARTING:
- Item: {item_description}
- Your target price: ${target_price}
- Your maximum price: ${max_price}
- Strategy: {strategy.value.upper()}
- Provider: {provider_name}
- Provider's asking price: ${provider_initial_price}

This is the FIRST message. Create an opening offer or question.
If using AGGRESSIVE strategy, start low (maybe 60-70% of their ask).
If BALANCED, start around 75-85%.
If CONSERVATIVE, start around 85-90%.

Make your opening move.
"""

    result = await get_negotiator_agent().run(prompt)
    return result.output
