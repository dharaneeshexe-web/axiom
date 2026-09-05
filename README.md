# Axiom

**commerce, decided.**

An autonomous agent that completes purchases on a buyer's behalf using Razorpay test-mode APIs — with every money action **explainable, bounded, and gated**, and graceful handling of payment failures. Built for the Razorpay AI Buildathon, Track 01: AI Growth & Agentic Commerce.

## What it does

Axiom is a conversational checkout agent. The user just says what they want to buy; Axiom browses the catalog, pins the right variant, confirms the price, creates a Razorpay order, and issues a bounded payment link. When a payment fails, Axiom explains *why* and recovers — not just blocks.

Every decision is traced to Laminar, so each money action can be audited end-to-end.

## Demo

The server serves a live cockpit at `/`:

- **Conversation** panel — user/agent bubbles with clickable variant chips and a stage pill (`BROWSE → SELECT → CONFIRM → EXECUTE → DONE`)
- **Agent Decision Trace** panel — live Laminar spans, status-coded, with an "Open in Laminar" link
- **Order & Catalog** panel — selected SKU, payment status, clickable payment link, grouped catalog
- **Browser voice** — hands-free STT (`webkitSpeechRecognition`) + spoken replies (`speechSynthesis`), ₹0, no new accounts
- **Quick-scenario launchers** — iPhone / Bandage / Ice Cream Cake / Failure Recovery

## Architecture

```
            USER (chat / voice / dashboard)
                       │
                       ▼
              FASTAPI SERVER  (src/api/endpoints.py)
        ┌────────────┬─────────────┬─────────────┐
        ▼            ▼             ▼             ▼
   Stateful    Intent       Catalog      Laminar
   ChatSession  Parser       Service      Tracer
   (BROWSE→     (Groq,       (48 products, (agent-native
    SELECT→      qwen3.8-    grouped)      audit trail)
    CONFIRM→    27b)
    EXECUTE→
    DONE)
        │            │              │
        └────────────┴──────┬───────┘
                            ▼
                     Razorpay Test API
                  (order → payment_link)
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI (async) |
| Agent state | Stateful multi-turn session (stage machine) + legacy LangGraph `/checkout` |
| LLM | Groq `qwen/qwen3.8-27b` (clean JSON, fast) |
| Payments | Razorpay Test Mode → Payment Links |
| Tracing | Laminar (`lmnr`) — every decision span |
| Frontend | Single static bundle (no build step) + browser voice |
| Deploy | Docker (python:3.12-slim), Railway-ready |

## Features

- **Conversational multi-turn checkout** — browse → select → confirm → pay
- **Intent parsing** — natural language → structured product request (Pydantic-validated, hallucination-checked against catalog)
- **Payment failure recovery** — card declined → auto-retry with UPI
- **Graceful failure** — every money action is explainable, bounded, and gated; failures return clean replies, never a crash
- **Laminar audit trail** — full transcript of every decision, with an error span on failed money actions
- **Protocol awareness** — built with NPCI UAP / Google AP2 / Coinbase x402 in mind
- **Browser voice** — free STT + TTS, no new keys

## Setup

### 1. Clone and install

```bash
git clone https://github.com/dharaneeshexe-web/axiom
cd axiom
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -e .
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

```
RAZORPAY_KEY_ID=rzp_test_xxxx
RAZORPAY_KEY_SECRET=xxxx
GROQ_API_KEY=gsk_xxxx
LAMINAR_API_KEY=xxxx
DEMO_FAILURE=none
MAX_RETRIES=3
```

Never commit `.env` (it is gitignored and dockerignored).

### 3. Run

```bash
uvicorn src.api.endpoints:app --host 0.0.0.0 --port 8000
```

or with Docker:

```bash
docker-compose up --build
```

Open `http://localhost:8000` for the live dashboard.

### 4. Try the conversational agent

```bash
# start a session
curl http://localhost:8000/chat

# message the agent: SESSION_ID from above
curl -X POST http://localhost:8000/chat/<SESSION_ID>/message \
  -H "Content-Type: application/json" \
  -d '{"query": "Place an order for iPhone 16, show me options"}'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Live demo dashboard (static bundle) |
| `/chat` | GET | Start a chat session |
| `/chat/{session_id}/message` | POST | Send a message to the agent |
| `/chat/{session_id}/state` | GET | Current session state |
| `/catalog` | GET | Products grouped by category |
| `/checkout` | POST | Legacy single-shot LangGraph checkout |
| `/traces` | GET | All traces (in-memory) |
| `/traces/{trace_id}` | GET | Specific trace |
| `/health` | GET | Health check |

## Failure Scenarios

| Scenario | Simulated via `DEMO_FAILURE` | Agent response |
|----------|------|----------------|
| Card declined | `card_declined` | Explains "card declined", auto-retries with UPI → success |
| Insufficient funds | `insufficient_funds` | Explains, no crash — graceful give-up |
| Expired card | `expired_card` | Explains, asks user to update |
| Processing error | `processing_error` | Explains, bounded retry |
| Rate limit (429) | real Razorpay test-mode cap | Fast, graceful, precise message — no 52s hang |

## Project Structure

```
src/
├── agent/
│   ├── session.py         # ChatSession stage machine (multi-turn)
│   ├── intent_parser.py   # Groq intent parsing (async-safe, key rotation)
│   └── workflow.py        # Legacy LangGraph agent
├── services/
│   ├── razorpay.py        # Razorpay client (retry/backoff, error mapping)
│   ├── catalog.py         # 48 products, 5 categories
│   ├── order.py           # Order management
│   └── payment.py         # Payment processing
├── models/schemas.py      # Pydantic models
├── config/
│   ├── settings.py        # Env config (extra="ignore")
│   └── tracing.py         # Laminar tracer (bounded store)
└── api/endpoints.py       # FastAPI routes
```

## Honest note on Razorpay test mode

Razorpay test mode caps `payment_links` at **30/day**. Once reached, the money step returns `429 RATE_LIMIT_EXCEEDED`. Axiom handles this gracefully and fast — it surfaces the real reason and exits cleanly instead of hanging. The limit resets daily. The failure-recovery demo (`DEMO_FAILURE=card_declined`) is simulated and not rate-limited, so it always shows a clean success path.

## License

MIT
