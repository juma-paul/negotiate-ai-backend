# NegotiateAI

**Multi-Agent Parallel Negotiation System**

Deploy AI agents that negotiate with multiple providers simultaneously to find you the best price.

[Live Demo](https://frontend-ten-wine-44.vercel.app) | [API Docs](https://negotiate-ai-backend.onrender.com/docs)

---

## The Problem

**Manual negotiation is slow, exhausting, and leaves money on the table.**

When you need a service (shipping, contractors, hotels, insurance), you either:
- Accept the first price you're offered
- Spend hours calling multiple vendors, repeating yourself
- Hire a broker who takes 10-15% commission

What if you could have 5 expert negotiators working for you simultaneously, in seconds?

---

## The Solution

NegotiateAI deploys multiple AI agents that:

1. **Negotiate in Parallel** - Talk to 5-10 providers at once
2. **Use Proven Strategies** - Aggressive, balanced, or conservative approaches
3. **Stream Real-Time Updates** - Watch every offer and counter-offer live
4. **Find the Best Deal** - Automatically identify the lowest accepted price

```
You: "Freight shipment LA→Chicago, target $3,000, max $4,000"

┌─────────────────────────────────────────────────────────────┐
│  Agent 1 → QuickShip (FIRM)      │ Started at $4,200       │
│  Agent 2 → FastFreight (FLEXIBLE) │ Negotiated to $2,800 ✓ │ ← BEST DEAL
│  Agent 3 → Budget Haulers (DESP) │ Accepted $2,950 ✓       │
│  Agent 4 → Premium Trans (PREM)  │ Rejected, too low       │
│  Agent 5 → Lightning (FLEXIBLE)  │ Negotiated to $2,900 ✓  │
└─────────────────────────────────────────────────────────────┘

Result: Saved $1,400 (33% below initial asking) in under 30 seconds
```

---

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    React Dashboard                           │
│              Real-time negotiation visualization             │
└─────────────────────────┬───────────────────────────────────┘
                          │ SSE (Server-Sent Events)
┌─────────────────────────▼───────────────────────────────────┐
│                   FastAPI Backend                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           Orchestrator (coordinates all agents)         │ │
│  └────────────────────────────────────────────────────────┘ │
│          │              │              │              │      │
│   ┌──────▼───┐   ┌──────▼───┐   ┌──────▼───┐   ┌──────▼───┐ │
│   │Negotiator│   │Negotiator│   │Negotiator│   │Negotiator│ │
│   │ Agent 1  │   │ Agent 2  │   │ Agent 3  │   │ Agent N  │ │
│   └──────┬───┘   └──────┬───┘   └──────┬───┘   └──────┬───┘ │
│          │              │              │              │      │
│   ┌──────▼───┐   ┌──────▼───┐   ┌──────▼───┐   ┌──────▼───┐ │
│   │ Provider │   │ Provider │   │ Provider │   │ Provider │ │
│   │  (FIRM)  │   │(FLEXIBLE)│   │(DESPERATE│   │ (PREMIUM)│ │
│   └──────────┘   └──────────┘   └──────────┘   └──────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Component | Technology |
|-----------|------------|
| AI Framework | **Pydantic AI** - Structured outputs, type safety |
| LLM | OpenAI GPT-4o-mini |
| Backend | FastAPI + Python 3.11 |
| Frontend | Next.js 14 + TypeScript + Tailwind |
| Real-time | Server-Sent Events (SSE) |
| Package Manager | uv (backend), npm (frontend) |
| Deployment | Render (API) + Vercel (Frontend) |

---

## Features

### Core Features

- **Parallel Agent Execution** - All negotiations run concurrently
- **Structured AI Outputs** - Every response is typed and validated
- **Real-Time Streaming** - Watch negotiations unfold live
- **Multiple Strategies** - Aggressive, balanced, conservative
- **Provider Personalities** - Firm, flexible, desperate, premium

### Production Features

- **Secure Session IDs** - 128-bit cryptographic tokens
- **Rate Limiting** - Protection against abuse
- **Input Validation** - Prompt injection protection
- **Timeouts & Fallbacks** - Graceful error handling
- **SSE Heartbeats** - Connection keep-alive
- **Auto-Reconnection** - Frontend reconnects on disconnect

---

## Is This Agents Talking to Agents or Humans?

**In this demo: Agent ↔ Agent (simulated)**

```
┌─────────────────┐         ┌─────────────────┐
│   Negotiator    │ ──────► │    Provider     │
│   (GPT-4o-mini) │ ◄────── │   (GPT-4o-mini) │
│   Works FOR you │         │   Simulates     │
│                 │         │   vendor        │
└─────────────────┘         └─────────────────┘
```

The provider is an AI simulating different vendor personalities. This demonstrates the negotiation patterns without requiring real API integrations.

**In production (like Lanesurf): Agent ↔ Human via Voice**

```
┌─────────────────┐         ┌─────────────────┐
│   AI Agent      │ ──────► │   Real Human    │
│   (Phone Call)  │ ◄────── │   (Carrier Rep) │
│                 │         │                 │
│   TTS → Speech  │         │   Listens       │
│   STT ← Hears   │         │   Speaks        │
└─────────────────┘         └─────────────────┘
```

The same negotiation logic applies, but with:
- **Text-to-Speech (TTS)**: Agent speaks via phone
- **Speech-to-Text (STT)**: Agent understands human responses
- **Interruption Handling**: Agent knows when to pause/continue
- **Tone Adaptation**: Agent adjusts based on conversation sentiment

---

## Voice Integration (Phase 2)

This project is architected to add voice capabilities:

### Adding TTS (Text-to-Speech)

```python
from openai import OpenAI

async def speak_message(text: str) -> bytes:
    """Convert negotiator message to speech."""
    client = OpenAI()
    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",  # or "nova", "echo", etc.
        input=text
    )
    return response.content  # Audio bytes
```

### Adding STT (Speech-to-Text)

```python
async def transcribe_response(audio_bytes: bytes) -> str:
    """Convert provider's voice to text."""
    client = OpenAI()
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=("audio.wav", audio_bytes),
        response_format="text"
    )
    return transcript
```

### Full Voice Loop

```
User Request
     │
     ▼
┌────────────────────────────────────────────────┐
│  1. Agent decides what to say (GPT-4o)         │
│  2. Convert to speech (TTS)                    │
│  3. Play audio over phone call                 │
│  4. Listen for response                        │
│  5. Transcribe response (Whisper)              │
│  6. Parse and understand (GPT-4o)              │
│  7. Repeat until deal or walk away             │
└────────────────────────────────────────────────┘
     │
     ▼
Deal Found or Negotiation Ended
```

---

## Real-World Use Cases

### 1. Freight & Logistics (Lanesurf's Market)

**Problem**: Freight brokers manually call 50-100 trucking companies to find capacity and negotiate rates. This takes hours.

**Solution**: AI agents call carriers simultaneously, negotiate rates, and book the best option.

```
Input: "40ft container, LA to Chicago, need pickup tomorrow"

AI calls 96 carriers at once:
- 34 don't answer
- 42 don't have capacity
- 20 have capacity, negotiate prices
- Best deal: $2,800 with FastFreight (normally $3,500)

Time saved: 3 hours → 90 seconds
```

### 2. Hotel & Travel Booking

**Problem**: Hotels have unpublished rates. You get different prices calling vs. booking online.

**Solution**: AI agents call hotels directly, negotiate room rates, ask about upgrades.

```
Input: "4-night stay in NYC, prefer Times Square area"

AI contacts 10 hotels simultaneously:
- Marriott: $450/night → negotiated to $380/night
- Hilton: $420/night → negotiated to $350/night ← BEST
- Hyatt: $400/night → wouldn't budge

Savings: $280 over 4 nights
```

### 3. Home Services & Contractors

**Problem**: Getting quotes from multiple contractors is tedious. You repeat your project details 10 times.

**Solution**: AI describes your project to multiple contractors, negotiates pricing.

```
Input: "Bathroom remodel, 100 sqft, new tiles, vanity, toilet"

AI contacts 8 contractors:
- Contractor A: $15,000 → $12,500
- Contractor B: $18,000 → wouldn't budge (PREMIUM)
- Contractor C: $11,000 → $9,800 ← BEST (DESPERATE for work)

Savings: $5,200 vs. first quote
```

### 4. Insurance Quotes

**Problem**: Insurance shopping requires filling out 10 forms with the same information.

**Solution**: AI speaks with insurance agents, provides your info once, compares quotes.

```
Input: "Auto insurance, 2022 Tesla Model 3, clean driving record"

AI contacts 6 insurers:
- State Farm: $180/month
- Progressive: $165/month → $145/month with bundling
- GEICO: $155/month → $140/month ← BEST

Savings: $480/year
```

### 5. B2B Software Procurement

**Problem**: Enterprise software pricing is opaque. Sales reps don't give straight answers.

**Solution**: AI negotiates with multiple vendors, plays them against each other.

```
Input: "CRM for 50 users, need API access, 2-year contract"

AI negotiates with 4 vendors:
- Salesforce: $150/user/month → $120/user/month
- HubSpot: $100/user/month → $80/user/month ← BEST
- Zoho: $45/user/month (no negotiation needed)
- Pipedrive: $60/user/month → $50/user/month

Best value: HubSpot at $4,000/month (was $7,500 at Salesforce)
```

### 6. Medical Bills

**Problem**: Hospital bills are negotiable but most people don't know. 80% of bills have errors.

**Solution**: AI reviews bills, contacts billing departments, negotiates reductions.

```
Input: "ER visit bill, $4,500, uninsured"

AI contacts billing department:
- Identifies $800 in duplicate charges
- Negotiates uninsured discount: 40% off
- Sets up payment plan

Final: $2,220 (saved $2,280)
```

### 7. Car Buying

**Problem**: Dealerships are adversarial. You never know if you got a good deal.

**Solution**: AI contacts multiple dealerships, negotiates out-the-door price.

```
Input: "2024 Honda CR-V EX, white, looking to buy this week"

AI contacts 6 dealerships:
- Dealer A: MSRP $35,000 → $33,500 OTD
- Dealer B: $34,200 → $32,800 OTD ← BEST
- Dealer C: Won't negotiate (FIRM)

Savings: $2,200 off MSRP
```

### 8. Salary Negotiation

**Problem**: Most people don't negotiate job offers. They leave $5,000-$20,000 on the table.

**Solution**: AI practices negotiations with you, or negotiates on your behalf.

```
Input: "Software engineer offer, $150K base, want $170K"

AI coaching mode:
- Practices counter-offer phrasing
- Simulates HR pushback scenarios
- Provides research on market rates

Result: User negotiates $165K + $10K signing bonus
```

---

## Why This Matters

### The Numbers

| Metric | Manual | NegotiateAI |
|--------|--------|-------------|
| Time per negotiation | 30-60 min | 30-90 sec |
| Providers contacted | 3-5 | 5-10 simultaneously |
| Average savings | 5-10% | 15-30% |
| Emotional energy | High | Zero |

### The Future

This technology is already being deployed:
- **Lanesurf** - AI calls 96 trucking companies simultaneously
- **Regal.ai** - AI handles sales calls
- **Air AI** - AI customer service agents

The pattern is the same:
1. **Structured AI outputs** → Agent knows exactly what to say
2. **Parallel execution** → Scale to hundreds of conversations
3. **Real-time streaming** → Humans monitor and intervene if needed
4. **Voice integration** → Natural phone conversations

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- OpenAI API key

### Backend

```bash
cd backend
uv sync
echo "OPENAI_API_KEY=sk-xxx" > .env
uv run python run.py
```

### Frontend

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

Open http://localhost:3000

---

## API Reference

### Create Negotiation

```bash
POST /api/negotiate
{
  "item_description": "Freight shipment LA to Chicago",
  "target_price": 2500,
  "max_price": 3500,
  "num_providers": 5,
  "strategy": "balanced"
}
```

### Stream Updates

```bash
GET /api/negotiate/{session_id}/stream
# Returns SSE stream with events:
# - heartbeat: Connection alive
# - message: Negotiation update
# - deal_found: Provider accepted
# - completed: All negotiations done
```

### Get Session State

```bash
GET /api/negotiate/{session_id}
# Returns current session with all provider states
```

---

## Project Structure

```
negotiate-ai/
├── backend/
│   ├── src/
│   │   ├── config.py       # Settings & logging
│   │   ├── models.py       # Pydantic data structures
│   │   ├── negotiator.py   # AI agent that negotiates FOR you
│   │   ├── providers.py    # Simulated vendors
│   │   ├── orchestrator.py # Parallel coordination
│   │   └── main.py         # FastAPI endpoints
│   ├── tests/
│   ├── pyproject.toml
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/api.ts      # SSE client
│   │   └── types/
│   ├── package.json
│   └── next.config.ts
├── LEARNING.md             # Step-by-step tutorial
└── README.md
```

---

## Deployment

### Backend (Render)

1. Connect GitHub repo
2. Set environment variables:
   - `OPENAI_API_KEY`
   - `ALLOWED_ORIGINS` (your frontend URL)
3. Build command: `pip install -e .`
4. Start command: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`

### Frontend (Vercel)

1. Connect GitHub repo
2. Set environment variable:
   - `NEXT_PUBLIC_API_URL` (your backend URL)
3. Deploy

---

## License

MIT

---

## Author

Built as a portfolio project for the Lanesurf Agent Engineer position.

Demonstrates:
- Multi-agent AI systems with Pydantic AI
- Real-time streaming with SSE
- Production-ready FastAPI backend
- Modern React frontend with TypeScript
- Full deployment pipeline

---

*"The best negotiator is one who never gets tired, never gets emotional, and can talk to 100 people at once."*
