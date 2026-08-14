"""
Production scheduling metadata service.

This is the source of truth for the data that makes the agent's bump
recommendation real rather than decorative: which shots are client-approved,
which have downstream dependents, and what priority they carry. It's
queryable two ways:
  - directly, by whatever builds a ShotEvent (ingest, the chaos injector)
  - indirectly via Loki, since every mutation is emitted as a structured log
    line (pipeline.common.telemetry.log_shot_event) that the agent's
    dependency/approval lookups query at investigate-time — the data lives in
    the observability stack, not in a side channel the agent can't see.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import FastAPI
from pydantic import BaseModel

from pipeline.common.models import PriorityTag, ShotEvent
from pipeline.common.telemetry import get_logger, log_shot_event

app = FastAPI()
logger = get_logger("scheduler")

# In-memory for the hackathon demo; swap for Firestore if this needs to
# survive restarts or run with more than one instance.
_shots: dict[str, ShotEvent] = {}


class NewShotRequest(BaseModel):
    episode_id: str
    depends_on: list[str] = []
    client_approved: bool = False
    priority_tag: PriorityTag = "standard"
    deadline_in_hours: float = 6.0


@app.post("/shots")
def create_shot(req: NewShotRequest) -> ShotEvent:
    shot_id = str(uuid.uuid4())[:8]
    event = ShotEvent(
        shot_id=shot_id,
        episode_id=req.episode_id,
        stage="ingest",
        status="queued",
        depends_on=req.depends_on,
        client_approved=req.client_approved,
        priority_tag=req.priority_tag,
        deadline=datetime.utcnow() + timedelta(hours=req.deadline_in_hours),
    )
    _shots[shot_id] = event
    log_shot_event(logger, event, "shot metadata registered")
    return event


@app.get("/shots/{shot_id}")
def get_shot(shot_id: str) -> ShotEvent:
    return _shots[shot_id]


@app.get("/episodes/{episode_id}/shots")
def list_episode_shots(episode_id: str) -> list[ShotEvent]:
    matches = [s for s in _shots.values() if s.episode_id == episode_id]
    for s in matches:
        log_shot_event(logger, s, "shot metadata snapshot")  # keeps Loki fresh for the agent
    return matches


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
