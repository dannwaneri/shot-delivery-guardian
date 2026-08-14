"""
Chaos injector: deterministically creates the render-backlog scenario the
demo needs, instead of hoping the simulated pipeline happens to fall behind
on camera. Trigger manually (curl/Postman) or wire to Cloud Scheduler for a
repeatable rehearsal before recording.

Replace the REPLACE placeholders with the actual Cloud Run URLs after
`infra/deploy.sh` runs (or read them from env vars — left as literals here
so the demo-trigger shape is obvious at a glance).
"""
from __future__ import annotations

import os

import httpx
from fastapi import FastAPI

app = FastAPI()

INGEST_URL = os.environ.get("INGEST_URL", "https://shot-ingest-REPLACE.run.app/ingest")
SCHEDULER_URL = os.environ.get("SCHEDULER_URL", "https://shot-scheduler-REPLACE.run.app/shots")


@app.post("/inject-backlog")
def inject_backlog(episode_id: str = "ep04", shot_count: int = 25):
    """Registers `shot_count` shots for `episode_id` fast enough to outrun
    render throughput and trip the deadline-risk alert within a predictable
    window. Roughly a third are pre-approved, every 7th is director-flagged,
    and every 5th shot depends on the previous one — enough variation for the
    bump-scoring rule to have real choices to make."""
    created: list[dict] = []
    with httpx.Client(timeout=10) as client:
        for i in range(shot_count):
            depends_on = [created[-1]["shot_id"]] if created and i % 5 == 0 else []
            meta = client.post(
                SCHEDULER_URL,
                json={
                    "episode_id": episode_id,
                    "depends_on": depends_on,
                    "client_approved": i % 3 == 0,
                    "priority_tag": "director_flagged" if i % 7 == 0 else "standard",
                    "deadline_in_hours": 1.0,
                },
            ).json()
            client.post(INGEST_URL, json=meta)
            created.append(meta)
    return {"injected": len(created), "episode_id": episode_id}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
