# Frontend Context — Handoff for Antigravity

You are being handed the **frontend** of "Axiom" — an agentic-commerce demo console for the
Razorpay AI Buildathon (Track 01). Read this file first, then the three frontend files, then
the API contract below. Do NOT modify backend Python code unless the task requires a tiny,
obvious API addition — and say so if you do.

---

## 1. What this product is (for design/narrative grounding)

Axiom is an **autonomous agent that completes purchases on a user's behalf** using Razorpay
test-mode APIs. A user tells the agent what to buy, the agent queries a catalog, shows
variants, confirms price, runs a **policy/approval/budget check**, creates a Razorpay order +
payment link, and (on failure) recovers gracefully (e.g. card declined → retry UPI).

Three things make it different from competitors (all must be visible in the UI):
1. **Policy engine** — real decisions (budget OK/OVER, approval AUTO/REQUIRED, preference
   card/UPI, merchant rule). Big purchases (≥ ₹50,000) PAUSE at confirm and require the user
   to reply "APPROVE" before money moves.
2. **Laminar audit trail** — every agent decision rendered as a live "decision trace"
   (parse_intent → query_catalog → select_product → policy_check → user_confirmation →
   create_order → process_payment), each with a per-stage duration in ms. "Truth" that every
   money action is explainable, bounded, gated.
3. **Failure recovery** — when a payment fails the agent retries (card → UPI) and the UI must
   show it recovered, not just "blocked".

Advertised branding: **"Axiom — commerce, decided."** Repo is `axiom`. NOTE: the current
frontend brand still says **"GrokCheckout"** (older name) — this is a branding mismatch to fix.

---

## 2. Architecture — read this, it constrains everything

- **FastAPI backend** (`src/api/endpoints.py`) serves the SPA and all its data.
- The frontend is a **single static bundle with NO build step** (no Node, no bundler, no
  npm). It ships as three plain files served as static assets:
  - `src/static/index.html` (structure)
  - `src/static/app.js` (vanilla JS, IIFE, `"use strict"`)
  - `src/static/style.css` (single stylesheet)
- It must run inside a Docker container and from a plain `python -m uvicorn` — so keep it
  self-contained: **no CDN JS frameworks, no `<script src>` beyond app.js, no CSS preprocessor.
  Google Fonts via `<link>` is fine.**
- Verify JS syntax ONLY with `node --check src/static/app.js` (no running it). There is NO
  frontend test runner. Static files are served at `/static/*`; the app is at `/`.

File sizes today: `index.html` 145 lines, `app.js` 525 lines, `style.css` 410 lines.

---

## 3. Existing UI layout (current, working)

Dark "cockpit" console on a 3-column grid, plus a header, a quick-scenario row, and a
merchant-metrics strip:

```
Header:  ◈ GrokCheckout · Agentic Commerce Console      (●) Live · Razorpay Test Mode
Quick chips:  [iPhone 16]  [Crepe Bandage]  [Ice Cream Cake]  [Failure Recovery]
Grid (3 cols, ~equal):
  Col 1 — Conversation   : chat log (user/agent bubbles), stage pill, variant chips,
                           mic (STT) button, VOICE toggle, Send
  Col 2 — Agent Decision Trace : live Laminar spans (status/duration), "Open in Laminar ↗"
  Col 3 — Order & Catalog: SKU card, payment box (status+pay link), Policy/Decision-Graph
                           box, "Browse catalog" collapsible group
Strip — Merchant Health   : Orders, Conversion %, Recovery rate %, Revenue recovered, S/F/R
```

Stage machine driving the stage pill: `browse → select → confirm → execute → done`.

---

## 4. Backend API contract the frontend depends on (exact)

Base: same origin as the page. All JSON.

- `GET /chat` → start session → `{ session_id, message }`
- `POST /chat/{session_id}/message` body `{ "query": "..." }` → `ChatOut` (see below)
- `GET /chat/{session_id}/state` → `ChatOut`
- `GET /traces/{trace_id}` → `{ spans: [ Span ] }`, each Span: `{ name, status, start_time,
  attributes: { duration_ms, ... } }`
- `GET /metrics` → `{ total_orders, conversion_rate_pct, recovery_rate_pct,
  revenue_recovered_paise, succeeded, failed, recovered, stage_latency_ms: {...} }`
- `GET /catalog` → `{ "<Category>": [ CatalogItem ... ] }`
- `GET /payment-mode` → `{ mode: "live" | "simulate" }`
- `POST /payment-mode` body `{ "mode": "live"|"simulate" }` → `{ mode }`
- `GET /health` → health
- `GET /` → index.html (the SPA itself)

**`ChatOut` shape** (the object `handleReply(data)` receives):
```
{
  session_id, message, stage: "browse|select|confirm|execute|done",
  options: [ { label, summary, price_rupees, item_id } ],   // variant chips (stage=select)
  success: bool,
  order_id?, amount?, currency?, payment_link?, trace_id?, payment_status?, error?,
  product_name?, product_summary?, product_emoji?,
  policy?: {
    approved, requires_approval, over_budget,
    reason?, remaining_budget?, suggested_actions: [], merchant_rule?, decisions: []
  },
  latency_ms?
}
```

`app.js` currently hardcodes:
- `LAMINAR_PROJECT = "ed6e32ed-eb7f-4fd0-aae6-fdc5476dc4b4"` → builds the "Open in Laminar"
  trace URL. Keep it.
- Quick-scenario launch text in `SCENARIOS` (iphone/bandage/cake/failure).

---

## 5. Current design system (`style.css`)

- Fonts: **Space Grotesk** (display/sans) + **IBM Plex Mono** (labels/numbers), via Google Fonts.
- Dark palette via CSS variables: `--bg:#0b0d10`, `--panel:#14171d`, `--panel-2:#181c23`,
  `--line:rgba(255,255,255,.07)`, `--text:#e8eaf0`, `--text-dim:#9aa1af`,
  `--text-faint:#5c6370`, `--accent:#34d399` (green), `--danger:#f87171`, `--warn:#fbbf24`.
- Rounded panels (14–18px radius), 1px hairline borders, green accent for money/success,
  pulsing live dot, mono labels on everything technical.
- A `_muted`, `.trace-dur` (accent-green latency), `.rule-badge ok/warn/danger`, and secret-ish
  class names already exist.

There is only ONE stylesheet and it is the single source of visual truth.

---

## 6. Known gaps this agent could own (choose scope with the human)

1. **Branding fix:** "GrokCheckout" → **Axiom**, tagline "commerce, decided."; page `<title>`
   too. Header + brand.
2. **Payment-mode visibility:** a "SIMULATE / LIVE" indicator + one-click toggle in the header
   (currently only controllable via chat command "don't call razorpay api" / `POST /payment-mode`
   — there's NO button in the UI). The header label "Live · Razorpay Test Mode" is now
   inaccurate in simulate mode. Tie it to `GET/POST /payment-mode`.
3. **Decision-graph visualization (P3 unfinished):** the policy box already renders a flat
   "Decision Graph" with step chips + badges; a richer visual (e.g. budget bar, approval/over-
   budget callouts, suggested actions) would strengthen the "real decisions" story.
4. **Per-stage latency visual:** `/traces/{id}/stages` and `/metrics.stage_latency_ms` exist
   but the trace panel only shows each span's ms inline — a mini timing bar/sparkline per stage
   would be a strong demo beat.
5. **Polish/responsiveness:** the 3-col grid collapses below 1100px only; check 3-col looks
   right on a 1080p demo screen and doesn't overflow.

---

## 7. Guardrails (important)

- **Zero new build steps.** No npm, no bundler, no framework CDN. Edit the 3 static files only.
- Keep the exact DOM hooks `app.js` uses (`#chatLog`, `#stagePill`, `#skuCard`, `#payBox`,
  `#policyBox`, `#traceLog`, `#laminarLink`, `#chatInput`, `#micBtn`, `#voiceBtn`,
  `#catBtn`, `#catalog`, `#catGroups`, `#metricsGrid`, `#metricsRefresh`) unless you move them
  deliberately and update `app.js` in the same change.
- Verify every change with: `node --check src/static/app.js` → clean; and confirm the running
  server still serves `/` and `/static/style.css` (200) with no JS console errors. Test the
  flows headlessly only if a browser harness is available (likely not) — otherwise rely on
  careful reading + `node --check`.
- Dark theme, green accent, mono labels, premium agency feel. Keep it cohesive — do not mix in
  a second accent color without checking the human.
- Do NOT commit/push anything unless explicitly told to.
- Windows console gotcha: if you run scripts that print ₹/emoji, set `PYTHONIOENCODING=utf-8`
  (only relevant for your own test scripts, not the product).

---

## 8. Files to read next (in order)

1. `src/static/index.html`
2. `src/static/app.js`
3. `src/static/style.css`
4. `src/api/endpoints.py` (for the exact response shapes / if you need a tiny API tweak)

Then confirm scope with the human (see section 6) before making large changes.
