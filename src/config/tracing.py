import uuid
import threading
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from ..config.settings import settings

try:
    from lmnr import Laminar
    _LMNR_AVAILABLE = True
except Exception:  # pragma: no cover - Laminar optional
    _LMNR_AVAILABLE = False


@dataclass
class TraceSpan:
    span_id: str
    name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str = "running"
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: list = field(default_factory=list)


class LaminarTracer:
    """Records spans to the real Laminar dashboard AND keeps a local store so the
    /traces endpoint stays available as a fallback."""

    def __init__(self):
        self.api_key = settings.laminar_api_key
        self.project_id = settings.laminar_project_id
        self._lock = threading.Lock()
        # local in-memory store (fallback for /traces endpoint)
        self.traces: Dict[str, list[TraceSpan]] = {}
        # trace -> {span_id -> real Laminar span object}
        self._laminar_spans: Dict[str, Dict[str, Any]] = {}
        # trace -> {span_id -> LaminarSpanContext (parent for nesting)}
        self._laminar_ctx: Dict[str, Dict[str, Any]] = {}
        # map our generated span_id back to a real base64 context for nesting
        self._initialized = False
        # bounding the in-memory store prevents unbounded growth over long demos
        self._max_traces = 200

    def _prune(self):
        # keep at most _max_traces newest traces (drop odd/old first, newest retained)
        if len(self.traces) > self._max_traces:
            excess = len(self.traces) - self._max_traces
            # insertion-ordered dict: pop the oldest entry
            for _ in range(excess):
                oldest = next(iter(self.traces))
                self.traces.pop(oldest, None)
                self._laminar_spans.pop(oldest, None)
                self._laminar_ctx.pop(oldest, None)

    def _ensure_initialized(self):
        if self._initialized or not _LMNR_AVAILABLE or not self.api_key:
            return
        try:
            Laminar.initialize(project_api_key=self.api_key)
            self._initialized = True
        except Exception:
            self._initialized = False

    def start_trace(self, trace_id: Optional[str] = None) -> str:
        self._ensure_initialized()
        if not trace_id:
            trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        with self._lock:
            self._prune()
            self.traces[trace_id] = []
            self._laminar_spans[trace_id] = {}
            self._laminar_ctx[trace_id] = {}
        return trace_id

    def start_span(
        self,
        trace_id: str,
        span_name: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        input: Any = None,
        session_id: Optional[str] = None,
        span_type: str = "DEFAULT",
    ) -> str:
        span_id = f"span_{uuid.uuid4().hex[:8]}"
        span = TraceSpan(
            span_id=span_id,
            name=span_name,
            start_time=datetime.utcnow(),
            attributes=attributes or {},
        )
        if parent_span_id:
            span.attributes["parent_span_id"] = parent_span_id

        with self._lock:
            if trace_id in self.traces:
                self.traces[trace_id].append(span)

        # Emit to real Laminar
        if _LMNR_AVAILABLE and self._initialized and trace_id in self._laminar_spans:
            try:
                parent_ctx = None
                if parent_span_id and trace_id in self._laminar_ctx:
                    parent_ctx = self._laminar_ctx[trace_id].get(parent_span_id)
                laminar_span = Laminar.start_active_span(
                    name=span_name,
                    input=input if input is not None else (attributes or {}),
                    parent_span_context=parent_ctx,
                    session_id=session_id,
                    span_type=span_type,
                    attributes=attributes or {},
                )
                with self._lock:
                    self._laminar_spans[trace_id][span_id] = laminar_span
                    try:
                        self._laminar_ctx[trace_id][span_id] = (
                            laminar_span.get_laminar_span_context()
                        )
                    except Exception:
                        pass
            except Exception:
                pass
        return span_id

    def end_span(
        self,
        trace_id: str,
        span_id: str,
        status: str = "completed",
        attributes: Optional[Dict[str, Any]] = None,
        output: Any = None,
    ):
        with self._lock:
            if trace_id in self.traces:
                for span in self.traces[trace_id]:
                    if span.span_id == span_id:
                        span.end_time = datetime.utcnow()
                        span.status = status
                        # P4: per-stage latency, computed from start/end (ms)
                        span.attributes["duration_ms"] = round(
                            (span.end_time - span.start_time).total_seconds() * 1000, 1
                        )
                        if attributes:
                            span.attributes.update(attributes)
                        break

        if (
            _LMNR_AVAILABLE
            and self._initialized
            and trace_id in self._laminar_spans
        ):
            try:
                laminar_span = self._laminar_spans[trace_id].get(span_id)
                if laminar_span is not None:
                    if attributes:
                        try:
                            laminar_span.set_attributes(attributes)
                        except Exception:
                            pass
                    if output is not None:
                        try:
                            laminar_span.set_output(output)
                        except Exception:
                            pass
                    if status != "completed":
                        try:
                            laminar_span.set_status(
                                "error" if status == "error" else status
                            )
                        except Exception:
                            pass
                    try:
                        laminar_span.end()
                    except Exception:
                        pass
            except Exception:
                pass

    def add_event(
        self,
        trace_id: str,
        span_id: str,
        event_name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        with self._lock:
            if trace_id in self.traces:
                for span in self.traces[trace_id]:
                    if span.span_id == span_id:
                        event = {
                            "name": event_name,
                            "timestamp": datetime.utcnow().isoformat(),
                            "attributes": attributes or {},
                        }
                        span.events.append(event)
                        break

        if (
            _LMNR_AVAILABLE
            and self._initialized
            and trace_id in self._laminar_spans
        ):
            try:
                laminar_span = self._laminar_spans[trace_id].get(span_id)
                if laminar_span is not None:
                    laminar_span.add_event(event_name, attributes or {})
            except Exception:
                pass

    def get_trace(self, trace_id: str) -> list[Dict[str, Any]]:
        if trace_id not in self.traces:
            return []
        trace_data = []
        for span in self.traces[trace_id]:
            trace_data.append(
                {
                    "span_id": span.span_id,
                    "name": span.name,
                    "start_time": span.start_time.isoformat(),
                    "end_time": span.end_time.isoformat() if span.end_time else None,
                    "status": span.status,
                    "attributes": span.attributes,
                    "events": span.events,
                }
            )
        return trace_data

    def get_all_traces(self) -> Dict[str, list]:
        return {tid: self.get_trace(tid) for tid in self.traces}

    # decision-graph stage order — used to present latency in a stable sequence
    STAGE_ORDER = [
        "parse_intent",
        "query_catalog",
        "select_product",
        "policy_check",
        "user_confirmation",
        "create_order",
        "process_payment",
        "handle_payment_failure",
    ]

    def stage_latency(self, trace_id: str) -> Dict[str, Any]:
        """Ordered per-stage latency breakdown for a trace (P4)."""
        spans = self.get_trace(trace_id)
        stages = {}
        for span in spans:
            if span["name"] not in self.STAGE_ORDER:
                continue
            stages[span["name"]] = {
                "duration_ms": span["attributes"].get("duration_ms", 0),
                "status": span["status"],
            }
        ordered = {k: stages[k] for k in self.STAGE_ORDER if k in stages}
        total = round(sum(v["duration_ms"] for v in ordered.values()), 1)
        return {"stages": ordered, "total_ms": total}

    def export_trace(self, trace_id: str) -> Dict[str, Any]:
        return {
            "trace_id": trace_id,
            "spans": self.get_trace(trace_id),
            "exported_at": datetime.utcnow().isoformat(),
        }


tracer = LaminarTracer()
