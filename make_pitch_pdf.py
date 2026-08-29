#!/usr/bin/env python3
"""Generate the Axiom pitch-script PDF."""
import os
from fpdf import FPDF

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "axion_pitch_script.pdf")

FONTS_DIR = r"C:\Windows\Fonts"
INK = (20, 20, 25)
ACCENT = (30, 60, 170)
MUTED = (110, 110, 120)


class PitchPDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 9)
        self.set_text_color(*MUTED)
        self.cell(0, 6, "AXIOM — PITCH SCRIPT   |   commerce, decided.", align="R")
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


pdf = PitchPDF(format="A4")
pdf.set_auto_page_break(auto=True, margin=18)
pdf.set_margins(20, 18, 20)

pdf.add_font("Arial", "", os.path.join(FONTS_DIR, "arial.ttf"))
pdf.add_font("Arial", "B", os.path.join(FONTS_DIR, "arialbd.ttf"))
pdf.add_font("Arial", "I", os.path.join(FONTS_DIR, "ariali.ttf"))


def section(num, title, time_range, lines):
    pdf.add_page()
    pdf.set_font("Arial", "B", 20)
    pdf.set_text_color(*INK)
    pdf.cell(0, 10, f"{num}. {title}")
    pdf.ln(5)
    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 7, f"TIMING: {time_range}")
    pdf.ln(9)
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(0.4)
    y = pdf.get_y()
    pdf.line(20, y, 190, y)
    pdf.ln(9)

    pdf.set_font("Arial", "B", 11)
    pdf.set_text_color(*INK)
    pdf.cell(0, 7, "SAY:")
    pdf.ln(9)

    pdf.set_font("Arial", "", 11)
    pdf.set_text_color(*INK)
    for blk in lines:
        pdf.multi_cell(0, 6.5, f"\u201c{blk}\u201d")
        pdf.ln(2.5)


section(
    "0",
    "INTRO & HOOK",
    "0:00 - 0:30",
    [
        "Hi, I\u2019m Dharaneesh. I built an agent that makes a merchant genuinely "
        "transactable by an AI buyer \u2014 end to end. Most agent-checkout demos work only "
        "when everything goes right. Mine fails on purpose, so you can watch it recover. "
        "It\u2019s called Axiom \u2014 commerce, decided.",

        "Optional: why now \u2014 agent-to-agent commerce is the open problem of the year. "
        "NPCI\u2019s UAP is in development, Google\u2019s AP2 and Coinbase\u2019s x402 are "
        "live. The infrastructure is arriving; what\u2019s missing is agents that can "
        "actually finish a purchase safely. That\u2019s what I built.",
    ],
)


section(
    "1",
    "LIVE DEMO \u2014 HAPPY PATH (iPhone 16)",
    "0:30 - 1:40",
    [
        "Here\u2019s the live agent. I\u2019ll just speak to it \u2014 no canned buttons for "
        "the core flow.   (Axiom, order an iPhone 16, show me the options.)",

        "(WAIT) It shows six variants with prices \u2014 black, white, blue, pink, natural.   "
        "(Blue, 256 gig.)",

        "(WAIT) It pins the variant and shows a confirmation with the price before any money "
        "moves.   (Yes.)",

        "Watch the right side \u2014 that\u2019s the Agent Decision Trace. Every step streams "
        "live: intent parsed, catalog searched, product pinned, order created, payment "
        "issued. This is Laminar. Every money action is explainable, bounded, and gated \u2014 "
        "you can see exactly why the agent did what it did. There\u2019s an open-in-Laminar "
        "link for the full transcript.",

        "And here\u2019s the payment link \u2014 a bounded, payable link the buyer "
        "authorizes. That\u2019s the money action, gated behind confirmation.",
    ],
)


section(
    "2",
    "THE DIFFERENTIATOR \u2014 FAILURE RECOVERY",
    "1:40 - 2:30",
    [
        "Now the part that\u2019s different. Every other checkout agent I\u2019ve seen blocks "
        "when payment fails. Let me show you what mine does.",

        "   (Axiom, buy me a crepe bandage.)   (Small.)   (Yes.)",

        "(PAUSE at the decline \u2014 let it register.) Look \u2014 the card was declined. "
        "Instead of a dead end, the agent says so, then retries with UPI. It recovered the "
        "sale. That\u2019s a payment you\u2019d have lost. That\u2019s the difference between "
        "an agent that works when it works, and one you can trust with real revenue.",

        "Optional: I simulate the decline deterministically so you see it every time \u2014 "
        "same result, no flakiness.",
    ],
)


section(
    "3",
    "ARCHITECTURE",
    "2:30 - 3:30",
    [
        "Under the hood it\u2019s a stateful multi-turn session \u2014 a stage machine: "
        "BROWSE, SELECT, CONFIRM, EXECUTE, DONE. Three layers do three jobs.",

        "AI \u2014 intent parsing. The LLM turns \u2018crepe bandage for my sprain\u2019 "
        "into a structured request. Groq serves it fast, clean JSON.",

        "Deterministic logic \u2014 where I chose NOT to use AI. Product selection and "
        "pricing resolve against the real catalog, never the model \u2014 so it can\u2019t "
        "hallucinate an SKU or a price. The state machine owns the flow.",

        "Trust and money \u2014 Razorpay test mode for orders and payment links, and Laminar "
        "for the audit trail. Failed money actions are logged as error spans \u2014 honest, "
        "not hidden.",
    ],
)


section(
    "4",
    "STRENGTHS & HONEST LIMITS",
    "3:30 - 4:15",
    [
        "First, it runs. Dockerized, health-checked, verified end-to-end. I didn\u2019t "
        "hand-wave it.",

        "Second, it recovers from its own infrastructure. Razorpay\u2019s test mode throttles "
        "payment links at 30 a day. When I hit that, it used to hang for almost a minute then "
        "crash. Now it fails fast, explains the real error code, and exits cleanly. "
        "That\u2019s been battle-tested \u2014 because my own testing broke it.",

        "And it\u2019s honest about a real limit: that 30-a-day cap is real, resets daily, "
        "and I say so openly. The failure-recovery demo is simulated so the money step "
        "always shows a clean path without burning the quota.",
    ],
)


section(
    "5",
    "CLOSING & VISION",
    "4:15 - 4:45",
    [
        "I built Axiom for today \u2014 it works now, with real payments and a real audit "
        "trail. And I built it aware of tomorrow. The protocols are racing: NPCI\u2019s UAP, "
        "Google\u2019s AP2, Coinbase\u2019s x402. Axiom is designed with that in mind \u2014 "
        "an agent that can finish a bounded, authorised purchase is exactly what those "
        "protocols will need.",

        "Every money action explainable, bounded, and gated. One failure handled gracefully "
        "\u2014 actually, four, and one of them recovered revenue. That\u2019s the bar, and "
        "Axiom clears it.",

        "I\u2019m Dharaneesh. Thank you.",
    ],
)


# FINAL PAGE
pdf.add_page()
pdf.set_font("Arial", "B", 16)
pdf.set_text_color(*INK)
pdf.cell(0, 9, "DELIVERY & DEMO NOTES")
pdf.ln(11)

notes = [
    ("Deliver", [
        "Stay under 5:00 \u2014 cut the protocol intro beat if the demo runs long.",
        "The demo is the star \u2014 never cut the failure-recovery moment.",
        "Use the exact rubric words: money action, bounded, gated, audit trail.",
        "Point at the Laminar span stream \u2014 don\u2019t just name it.",
        "Do NOT read the script. Learn the beats, let the dashboard prompt you.",
        "Rehearse aloud 3\u20135 times. Pauses read as confident, not forgotten.",
    ]),
    ("Demo runbook (record)", [
        "Scenario 1 \u2014 iPhone: order \u2192 Blue/256 \u2192 confirm \u2192 yes \u2192 link + full trace.",
        "Scenario 2 \u2014 Bandage: order \u2192 small \u2192 yes \u2192 CARD DECLINED \u2192 retries UPI \u2192 success.",
        "Scenario 3 (bonus) \u2014 Cake: chocolate \u2192 yes \u2192 link + trace.",
        "Record 3\u20135 clean runs; keep a backup even if one stumbles.",
    ]),
    ("Anti-checklist", [
        "Don\u2019t burn real payment links rehearsing the same day \u2014 30/day cap is real.",
        "Don\u2019t type if voice works; keep the typed fallback ready if STT is flaky.",
        "Don\u2019t rush the declined\u2192recovered beat \u2014 it\u2019s the whole pitch.",
        "If something fails on camera, recover and explain, or cut to a backup.",
    ]),
    ("On-screen layout", [
        "Conversation panel + Agent Decision Trace + Order/Payment Link = the focus.",
        "Face cam top-right if used; keep the trace and payment link always readable.",
    ]),
]

for head, items in notes:
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 8, head.upper())
    pdf.ln(9)
    pdf.set_font("Arial", "", 10.5)
    pdf.set_text_color(*INK)
    for it in items:
        pdf.multi_cell(0, 6, f"\u2022  {it}")
        pdf.ln(1.5)
    pdf.ln(4)

pdf.output(OUT)
print("PDF written:", OUT)
