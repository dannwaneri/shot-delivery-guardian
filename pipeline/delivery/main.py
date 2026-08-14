"""Delivery/package stage. Terminal — simulates packaging to the streamer's
ingest spec (e.g. an IMF package) and marks the shot complete."""
from __future__ import annotations

from pipeline.common.stage_service import build_stage_app


def route(event):
    return None, None  # terminal


app = build_stage_app("delivery", route=route, min_duration_s=1.0, max_duration_s=2.5)
