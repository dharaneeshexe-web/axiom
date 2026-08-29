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
   (BROWSE→     (Groq,       (21 products, (agent-native
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
│   ├── catalog.py         # 21 products, 4 categories
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

## Pitch script

> The 5-minute buildathon pitch. Also available as a printable PDF — `axion_pitch_script.pdf` (see `make_pitch_pdf.py` to regenerate).

**0. INTRO & HOOK (0:00–0:30)**
> "Hi, I'm Dharaneesh. I built an agent that makes a merchant genuinely transactable by an AI buyer — end to end. Most agent-checkout demos work only when everything goes right. Mine fails on purpose, so you can watch it recover. It's called Axiom — commerce, decided."
>
> *Optional, why now:* "Agent-to-agent commerce is the open problem of the year — NPCI's UAP in development, Google's AP2 and Coinbase's x402 live. The infrastructure is arriving; what's missing is agents that can safely finish a purchase. That's what I built."

**1. LIVE DEMO — HAPPY PATH · iPhone 16 (0:30–1:40)**
> "Here's the live agent — I'll just speak to it. Axiom, order an iPhone 16, show me the options." *(6 variants, with prices)* "Blue, 256 gig." *(pins variant, shows price — no money moves yet)* "Yes."
>
> "Watch the right side — the Agent Decision Trace. Intent parsed, catalog searched, product pinned, order created, payment issued. This is Laminar. Every money action is explainable, bounded, and gated — you can see exactly why the agent acted. There's an open-in-Laminar link for the full transcript. And here's the payment link — bounded, payable, authorized. That's the money action, gated behind confirmation."

**2. THE DIFFERENTIATOR — FAILURE RECOVERY (1:40–2:30)**
> "Every other checkout agent I've seen blocks when payment fails. Watch mine. Axiom, buy me a crepe bandage." *(small → yes → CARD DECLINED)*
>
> "The card was declined. Instead of a dead end, the agent says so, then retries with UPI — it recovered the sale. That's a payment you'd have lost. That's the difference between an agent that works when it works, and one you can trust with real revenue."
>
> *Optional:* "I simulate the decline deterministically so you see it every time — same result, no flakiness."

**3. ARCHITECTURE (2:30–3:30)**
> "Under the hood it's a stateful multi-turn session — a stage machine: BROWSE → SELECT → CONFIRM → EXECUTE → DONE. Three layers: **AI** — intent parsing; Groq turns 'crepe bandage for my sprain' into structured JSON. **Deterministic logic** — where I chose *not* to use AI: product selection and pricing resolve against the real catalog, never the model, so it can't hallucinate an SKU or price. **Trust & money** — Razorpay test mode for orders and payment links, Laminar for the audit trail. Failed money actions are logged as error spans — honest, not hidden."

**4. STRENGTHS & HONEST LIMITS (3:30–4:15)**
> "It runs — Dockerized, health-checked, verified end-to-end. It recovers from its own infrastructure: Razorpay's test mode throttles payment links at 30 a day; when I hit that it used to hang a minute then crash, now it fails fast with the real error code. And it's honest about that cap — it's real, resets daily, and I say so. The failure-recovery demo is simulated so it always shows a clean path without burning the quota."

**5. CLOSING & VISION (4:15–4:45)**
> "I built Axiom for today — real payments, a real audit trail — and I built it aware of tomorrow. The protocols are racing: NPCI's UAP, Google's AP2, Coinbase's x402. An agent that can finish a bounded, authorized purchase is exactly what they'll need. Every money action explainable, bounded, and gated. One failure handled gracefully — actually four, and one recovered revenue. That's the bar, and Axiom clears it. I'm Dharaneesh. Thank you."

**Delivery & demo notes**
- Do NOT read the script — learn the beats, let the live dashboard prompt you.
- Never cut the failure-recovery moment; it's the pitch.
- Use the rubric words: *money action, bounded, gated, audit trail*.
- Scenario runbook: **iPhone** (order → Blue/256 → confirm → yes → link + trace) · **Bandage** (order → small → yes → declined → UPI → success) · **Cake** (bonus, chocolate → yes).
- Don't burn real payment links rehearsing the same day (30/day cap); use the simulated failure path for slides.
- Record 3–5 clean runs; keep a backup even if one stumbles.

## License

MIT
