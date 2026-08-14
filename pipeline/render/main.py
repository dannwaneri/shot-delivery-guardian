"""Render/comp stage. Deliberately the slowest stage — this is where a backlog
under load actually shows up as growing `render_queue_depth`."""
from __future__ import annotations

from pipeline.common.stage_service import build_stage_app


def route(event):
    return "shot-color", "color"


app = build_stage_app("render", route=route, min_duration_s=2.0, max_duration_s=8.0)
