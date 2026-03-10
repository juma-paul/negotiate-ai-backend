"""Voice negotiator - AI agent for phone call negotiations."""
import asyncio
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from ..config import get_settings, logger


class VoiceAction(BaseModel):
    """Structured action from voice negotiator."""
    action: str = Field(
        ...,
        description="Action type: greet, offer, counter, accept, reject, ask_question, walk_away"
    )
    amount: float | None = Field(
        None,
        description="Price amount for offers/counters"
    )
    message: str = Field(
        ...,
        description="Message to speak to the human (keep under 50 words for natural conversation)"
    )
    is_final: bool = Field(
        False,
        description="Whether this ends the negotiation"
    )


_voice_agent: Agent[None, VoiceAction] | None = None


def get_voice_agent() -> Agent[None, VoiceAction]:
    """Get the voice negotiation agent."""
    global _voice_agent
    if _voice_agent is None:
        settings = get_settings()
        _voice_agent = Agent(
            f"openai:{settings.openai_model}",
            output_type=VoiceAction,
            system_prompt="""You are an AI freight broker negotiating rates over the phone with trucking company dispatchers.

CONVERSATION STYLE:
- Speak naturally like a real phone conversation
- Keep responses SHORT (under 50 words) - this is a phone call, not an email
- Be professional but personable
- Use filler words occasionally ("well", "so", "you know")
- Acknowledge what they say before responding

NEGOTIATION APPROACH:
- Start by confirming the shipment details
- Ask about their availability and capacity
- Negotiate firmly but fairly toward target price
- Use techniques: bundling future loads, flexible timing, quick payment terms
- Know when to accept a good deal
- Know when to walk away from a bad deal

REMEMBER:
- You're calling THEM - be respectful of their time
- They're busy dispatchers with many calls
- Build rapport but stay focused on the deal
- If they're firm on price, try other value adds before walking away"""
        )
    return _voice_agent


async def create_greeting(
    item_description: str,
    provider_name: str,
) -> VoiceAction:
    """Create initial greeting for the call."""
    agent = get_voice_agent()
    settings = get_settings()

    prompt = f"""You're calling {provider_name} about a freight shipment.

Shipment: {item_description}

Create a brief, professional greeting to start the conversation.
Introduce yourself as an AI freight broker and mention the shipment.
Keep it under 30 words - you're starting a phone conversation."""

    try:
        result = await asyncio.wait_for(
            agent.run(prompt),
            timeout=settings.api_timeout
        )
        return result.output
    except Exception as e:
        logger.error(f"Voice greeting error: {e}")
        return VoiceAction(
            action="greet",
            message=f"Hi, this is an AI assistant calling about freight. I'm looking to ship from here to there. Do you have availability?",
            is_final=False
        )


async def process_human_response(
    item_description: str,
    target_price: float,
    max_price: float,
    provider_name: str,
    current_price: float | None,
    transcript: list[dict],
    human_said: str,
) -> VoiceAction:
    """Process human's spoken response and generate next action."""
    agent = get_voice_agent()
    settings = get_settings()

    # Format transcript
    transcript_text = "\n".join([
        f"{'You' if t['role'] == 'agent' else 'Dispatcher'}: {t['text']}"
        for t in transcript[-6:]  # Last 6 exchanges
    ])

    prompt = f"""Phone negotiation with {provider_name}

SHIPMENT: {item_description}
YOUR TARGET: ${target_price:,.2f}
YOUR MAX BUDGET: ${max_price:,.2f}
THEIR CURRENT PRICE: ${current_price:,.2f if current_price else 'Not quoted yet'}

CONVERSATION SO FAR:
{transcript_text}

DISPATCHER JUST SAID: "{human_said}"

Respond naturally to what they said. Remember:
- Keep response under 50 words
- If they quoted a price, negotiate toward your target
- If they asked a question, answer it
- If price is at or below your target, you can accept
- If price is above your max and they won't budge, walk away politely"""

    try:
        result = await asyncio.wait_for(
            agent.run(prompt),
            timeout=settings.api_timeout
        )
        return result.output
    except Exception as e:
        logger.error(f"Voice negotiation error: {e}")
        return VoiceAction(
            action="ask_question",
            message="Sorry, I missed that. Could you repeat what you said about the rate?",
            is_final=False
        )


async def create_closing(accepted: bool, final_price: float | None) -> VoiceAction:
    """Create closing message for the call."""
    if accepted and final_price:
        return VoiceAction(
            action="accept",
            amount=final_price,
            message=f"Great, we have a deal at ${final_price:,.2f}. I'll send over the confirmation details. Thanks for working with us!",
            is_final=True
        )
    else:
        return VoiceAction(
            action="walk_away",
            message="I understand. Unfortunately that's outside our budget for this lane. Thanks for your time, and we'll keep you in mind for future loads.",
            is_final=True
        )
