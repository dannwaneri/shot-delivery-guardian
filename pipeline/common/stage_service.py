"""
Factory for a generic pipeline stage service.

Each concrete stage (render/color/qc/delivery) is a thin config over this:
receive a ShotEvent via Pub/Sub push, simulate the work, update the
stage-scoped Prometheus metrics, emit a structured log, close the trace span,
then route the event to whatever comes next (or terminate, if `route`
returns None for the next topic).
"""
from __future__ import annotations

import os
import random
import time
from typing import Callable, Optional

from fastapi import FastAPI, Request

from pipeline.common.pubsub import decode_push_envelope, publish_shot_event
from pipeline.common.telemetry import (
    RENDER_QUEUE_DEPTH,
    STAGE_DURATION_SECONDS,
    STAGE_THROUGHPUT,
    get_logger,
    init_tracing,
    otlp_auth_header,
    log_shot_event,
    shot_span,
)

# event -> (next_topic, next_stage); next_topic=None means this is terminal
RouteFn = Callable[[object], tuple[Optional[str], Optional[str]]]


def build_stage_app(
    stage: str,
    route: RouteFn,
    min_duration_s: float = 1.0,
    max_duration_s: float = 4.0,
) -> FastAPI:
    app = FastAPI()
    logger = get_logger(stage)
    tracer = init_tracing(
        stage,
        otlp_endpoint=os.environ["OTLP_ENDPOINT"],
        headers=otlp_auth_header(
            os.environ["GRAFANA_INSTANCE_ID"],
            os.environ["GRAFANA_OTLP_TOKEN"],
        ),
    )

    @app.post("/pubsub/push")
    async def handle_push(request: Request):
        body = await request.json()
        event = decode_push_envelope(body)
        event.stage = stage
        RENDER_QUEUE_DEPTH.labels(stage=stage).inc()

        with shot_span(tracer, f"{stage}.process", event.shot_id, event.episode_id):
            duration = random.uniform(min_duration_s, max_duration_s)
            time.sleep(duration)

            next_topic, next_stage = route(event)
            event.status = "rejected" if (stage == "qc" and next_stage == "render") else "completed"

            STAGE_DURATION_SECONDS.labels(stage=stage, status=event.status).observe(duration)
            STAGE_THROUGHPUT.labels(stage=stage).inc()
            RENDER_QUEUE_DEPTH.labels(stage=stage).dec()
            log_shot_event(logger, event, f"shot processed at {stage}")

            if next_topic is not None:
                event.stage = next_stage
                event.status = "queued"
                publish_shot_event(next_topic, event)

        return {"status": "ok"}

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app
