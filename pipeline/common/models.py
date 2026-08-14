"""Shared data model that flows through every pipeline stage."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Stage = Literal["ingest", "render", "color", "qc", "delivery"]
Status = Literal["queued", "in_progress", "completed", "failed", "rejected"]
PriorityTag = Literal["standard", "director_flagged", "client_locked"]


class ShotEvent(BaseModel):
    shot_id: str
    episode_id: str
    stage: Stage
    status: Status
    depends_on: list[str] = Field(default_factory=list)
    client_approved: bool = False
    priority_tag: PriorityTag = "standard"
    deadline: datetime
    timestamp: datetime = Field(default_factory=datetime.utcnow)
