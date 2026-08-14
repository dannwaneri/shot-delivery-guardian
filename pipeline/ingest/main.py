"""
Ingest: entry point for new shots arriving into the pipeline (simulates
dailies/VFX-vendor delivery notifications landing in the studio's system).
Called over HTTP — by the chaos injector for demo purposes, or by whatever
real trigger (watch folder, vendor webhook) would replace it in production.
"""
from __future__ import annotations

from fastapi import FastAPI

from pipeline.common.models import ShotEvent
from pipeline.common.pubsub import publish_shot_event
from pipeline.common.telemetry import RENDER_QUEUE_DEPTH, get_logger, log_shot_event

app = FastAPI()
logger = get_logger("ingest")


@app.post("/ingest")
def ingest_shot(event: ShotEvent):
    event.stage = "render"
    event.status = "queued"
    RENDER_QUEUE_DEPTH.labels(stage="render").inc()
    log_shot_event(logger, event, "shot ingested")
    publish_shot_event("shot-render", event)
    return {"status": "queued", "shot_id": event.shot_id}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
