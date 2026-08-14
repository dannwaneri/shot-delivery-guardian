"""QC stage. Randomly rejects a fraction of shots back into render — this
rework loop is what makes trace-based bottleneck-finding (step 3 of the
agent's investigate loop) actually necessary instead of trivial."""
from __future__ import annotations

import random

from pipeline.common.stage_service import build_stage_app

REJECT_PROBABILITY = 0.15


def route(event):
    if random.random() < REJECT_PROBABILITY:
        return "shot-render", "render"
    return "shot-delivery", "delivery"


app = build_stage_app("qc", route=route, min_duration_s=1.0, max_duration_s=3.0)
