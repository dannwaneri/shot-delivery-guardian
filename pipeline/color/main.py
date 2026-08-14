"""Color/DI stage."""
from __future__ import annotations

from pipeline.common.stage_service import build_stage_app


def route(event):
    return "shot-qc", "qc"


app = build_stage_app("color", route=route, min_duration_s=1.0, max_duration_s=3.0)
