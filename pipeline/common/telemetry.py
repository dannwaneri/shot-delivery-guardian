"""
Instrumentation shape (deliberate — see docs/ARCHITECTURE.md for why):

- Prometheus metrics: aggregated at stage level only. Never label with shot_id —
  that's how a Prometheus-style TSDB turns into a cardinality bomb.
- Loki logs: labels stay low-cardinality (service, episode_id, stage, status).
  shot_id, depends_on, client_approved, priority_tag ride inside the JSON body
  and are queried with LogQL's `| json` filter instead of being promoted to an
  index label — Loki's index is label-based too, so the same anti-pattern
  applies there, not just on the metrics side.
- Tempo traces: shot_id is a span attribute. Traces are built for exactly this
  kind of high-cardinality, per-entity lookup.
"""
from __future__ import annotations

import base64
import json
import logging
import sys
import time
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram

# ---- metrics (stage-level only, no shot_id) --------------------------------

RENDER_QUEUE_DEPTH = Gauge(
    "render_queue_depth", "Shots currently queued or in-flight at a stage", ["stage"]
)
STAGE_THROUGHPUT = Counter(
    "stage_completions_total", "Completed shots per stage", ["stage"]
)
STAGE_DURATION_SECONDS = Histogram(
    "stage_duration_seconds",
    "Time spent processing a shot at a stage",
    ["stage", "status"],
)


# ---- structured JSON logging (Loki-friendly; shot identity lives in body) --

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "service": getattr(record, "service", "unknown"),
            "episode_id": getattr(record, "episode_id", None),
            "stage": getattr(record, "stage", None),
            "status": getattr(record, "status", None),
            # everything below is body content, NOT promoted to a Loki label
            "shot": getattr(record, "shot", None),
        }
        return json.dumps(payload)


def get_logger(service_name: str) -> logging.LoggerAdapter:
    logger = logging.getLogger(service_name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logging.LoggerAdapter(logger, {"service": service_name})


def log_shot_event(logger: logging.LoggerAdapter, event, message: str) -> None:
    logger.info(
        message,
        extra={
            "episode_id": event.episode_id,
            "stage": event.stage,
            "status": event.status,
            "shot": {
                "shot_id": event.shot_id,
                "depends_on": event.depends_on,
                "client_approved": event.client_approved,
                "priority_tag": event.priority_tag,
                "deadline": event.deadline.isoformat(),
            },
        },
    )


# ---- tracing (shot_id as a span attribute, not a label) --------------------

def otlp_auth_header(instance_id: str, api_token: str) -> dict[str, str]:
    """Grafana Cloud's OTLP endpoint uses HTTP Basic auth with the stack's
    numeric instance ID as the username and an API token as the password.
    Building the base64 value here means the token stays a plain, copy-paste
    value in .env - nobody has to hand-encode a credential themselves."""
    credentials = base64.b64encode(f"{instance_id}:{api_token}".encode()).decode()
    return {"Authorization": f"Basic {credentials}"}


def init_tracing(service_name: str, otlp_endpoint: str, headers: dict[str, str]) -> trace.Tracer:
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, headers=headers)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


@contextmanager
def shot_span(tracer: trace.Tracer, name: str, shot_id: str, episode_id: str):
    with tracer.start_as_current_span(name) as span:
        span.set_attribute("shot_id", shot_id)
        span.set_attribute("episode_id", episode_id)
        start = time.time()
        try:
            yield span
        finally:
            span.set_attribute("duration_seconds", time.time() - start)
