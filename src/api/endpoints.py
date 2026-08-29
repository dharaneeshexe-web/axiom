from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel
from typing import Optional
from ..agent import CheckoutAgent
from ..models.schemas import PaymentMethod, AgentState
from ..config.tracing import tracer, _LMNR_AVAILABLE
from lmnr import Laminar


@asynccontextmanager
async def lifespan(app: FastAPI):
    if _LMNR_AVAILABLE:
        tracer._ensure_initialized()
    yield


app = FastAPI(
    title="Conversational Checkout Agent",
    description="An autonomous agent that completes transactions on behalf of users using Razorpay",
    version="1.0.0",
    lifespan=lifespan,
)


class CheckoutRequest(BaseModel):
    query: str
    payment_method: Optional[str] = "card"


class CheckoutResponse(BaseModel):
    success: bool
    message: str
    order_id: Optional[str] = None
    payment_id: Optional[str] = None
    amount: Optional[int] = None
    currency: Optional[str] = None
    payment_link: Optional[str] = None
    trace_id: Optional[str] = None
    error: Optional[str] = None


@app.post("/checkout", response_model=CheckoutResponse)
async def checkout(request: CheckoutRequest):
    trace_id = tracer.start_trace()
    session_id = f"checkout-{trace_id}"

    span_id = tracer.start_span(
        trace_id,
        "checkout_request",
        attributes={"query": request.query, "payment_method": request.payment_method},
        input={"query": request.query, "payment_method": request.payment_method},
        session_id=session_id,
    )

    try:
        payment_method = PaymentMethod(request.payment_method)
    except ValueError:
        payment_method = PaymentMethod.CARD

    agent = CheckoutAgent()
    
    span_id2 = tracer.start_span(
        trace_id,
        "agent_run",
        parent_span_id=span_id,
        attributes={"payment_method": payment_method.value},
        input={"payment_method": payment_method.value},
        session_id=session_id,
    )

    final_state = await agent.run(request.query, payment_method, trace_id=trace_id)

    tracer.end_span(
        trace_id,
        span_id2,
        status="completed",
        output={
            "order_id": (final_state.get("order").order_id if final_state.get("order") else None),
            "payment_status": (final_state.get("payment").status.value if final_state.get("payment") else None),
        },
    )

    order = final_state.get("order")
    payment = final_state.get("payment")
    error = final_state.get("error")

    if error:
        tracer.end_span(trace_id, span_id, status="error", attributes={"error": error}, output={"error": error})
        return CheckoutResponse(
            success=False,
            message="Checkout failed",
            trace_id=trace_id,
            error=error,
        )

    tracer.end_span(trace_id, span_id, status="completed", attributes={
        "order_id": order.order_id if order else None,
        "payment_id": payment.payment_id if payment else None,
    }, output={
        "order_id": order.order_id if order else None,
        "payment_id": payment.payment_id if payment else None,
    })

    return CheckoutResponse(
        success=True,
        message="Checkout completed successfully",
        order_id=order.order_id if order else None,
        payment_id=payment.payment_id if payment else None,
        amount=order.amount if order else None,
        currency=order.currency if order else None,
        payment_link=payment.alias if payment else None,
        trace_id=trace_id,
    )


# ---- Multi-turn conversational chat ----

from ..agent.session import ChatSession, AgentReply, VariantOption

# session_id -> (last_active, ChatSession)
# Bounded to avoid an unbounded in-memory leak across repeated demo runs.
_sessions: dict[str, tuple[datetime, ChatSession]] = {}
_SESSION_TTL = timedelta(minutes=30)
_MAX_SESSIONS = 100


def _prune_sessions():
    # time-based eviction, then size cap (drop oldest first)
    now = datetime.utcnow()
    stale = [sid for sid, (ts, _) in _sessions.items() if now - ts > _SESSION_TTL]
    for sid in stale:
        del _sessions[sid]
    if len(_sessions) > _MAX_SESSIONS:
        order = sorted(_sessions.items(), key=lambda kv: kv[1][0])
        for sid, _ in order[: len(_sessions) - _MAX_SESSIONS]:
            del _sessions[sid]


def _touch_session(sid: str):
    entry = _sessions.get(sid)
    if entry:
        _sessions[sid] = (datetime.utcnow(), entry[1])


class VariantOut(BaseModel):
    label: str
    summary: str
    price_rupees: int
    item_id: str


class ChatOut(BaseModel):
    session_id: str
    message: str
    stage: str
    options: list[VariantOut] = []
    success: bool = False
    order_id: Optional[str] = None
    amount: Optional[int] = None
    currency: Optional[str] = None
    payment_link: Optional[str] = None
    trace_id: Optional[str] = None
    payment_status: Optional[str] = None
    error: Optional[str] = None
    product_name: Optional[str] = None
    product_summary: Optional[str] = None
    product_emoji: Optional[str] = None


def _to_out(session_id: str, r: AgentReply) -> ChatOut:
    out = ChatOut(
        session_id=session_id,
        message=r.text,
        stage=r.stage.value,
        options=[VariantOut(label=o.label, summary=o.summary, price_rupees=o.price_rupees, item_id=o.item_id) for o in r.options],
        success=r.success,
        order_id=r.order_id,
        amount=r.amount,
        currency=r.currency,
        payment_link=r.payment_link,
        trace_id=r.trace_id,
        payment_status=r.payment_status,
        error=r.error,
        product_name=r.product_name,
        product_summary=r.product_summary,
    )
    return out


class StartChatOut(BaseModel):
    session_id: str
    message: str


@app.get("/chat", response_model=StartChatOut)
async def start_chat():
    sess = ChatSession()
    _prune_sessions()
    _sessions[sess.session_id] = (datetime.utcnow(), sess)
    return StartChatOut(
        session_id=sess.session_id,
        message="Hi! I'm your shopping agent. Tell me what you'd like to order.",
    )


@app.post("/chat/start", response_model=StartChatOut)
async def start_chat_post():
    return await start_chat()


@app.post("/chat/{session_id}/message", response_model=ChatOut)
async def chat_message(session_id: str, request: CheckoutRequest):
    entry = _sessions.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")
    _sessions[session_id] = (datetime.utcnow(), entry[1])
    reply = await entry[1].process(request.query)
    return _to_out(session_id, reply)


@app.get("/chat/{session_id}/state", response_model=ChatOut)
async def chat_state(session_id: str):
    entry = _sessions.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")
    _touch_session(session_id)
    return _to_out(session_id, AgentReply(
        text=entry[1].stage.value, stage=entry[1].stage, success=True, trace_id=entry[1].trace_id,
    ))


@app.get("/traces")
async def get_traces():
    return tracer.get_all_traces()


@app.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    trace = tracer.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return tracer.export_trace(trace_id)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}


# ---- Catalog browse (powers the demo dashboard) ----
from ..services.catalog import CatalogService

_catalog_service = CatalogService()


class CatalogItemOut(BaseModel):
    item_id: str
    name: str
    description: str
    price: int
    merchant_name: str
    category: Optional[str] = None
    emoji: Optional[str] = None
    color: Optional[str] = None
    storage: Optional[str] = None
    size: Optional[str] = None
    flavor: Optional[str] = None


@app.get("/catalog", response_model=dict)
async def browse_catalog():
    grouped = _catalog_service.by_category()
    return {
        cat: [CatalogItemOut(
            item_id=p.item_id,
            name=p.name,
            description=p.description,
            price=p.price,
            merchant_name=p.merchant_name,
            category=p.category,
            emoji=p.emoji,
            color=p.color,
            storage=p.storage,
            size=p.size,
            flavor=p.flavor,
        ) for p in items]
        for cat, items in grouped.items()
    }

# ---- Static demo console ----
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(str(_STATIC_DIR / "index.html"))
