# Shot-Delivery Guardian

Built for the **Agentic Cinema: The Blockbuster Hackathon** — Grafana track.

An agent that watches a post-production studio's shot-delivery pipeline
(ingest → render/comp → color/DI → QC → package-for-delivery) via Grafana
Cloud, and when a shot is at risk of missing its delivery window, investigates
*why* and recommends which shot is actually safe to bump — computed from real
dependency/approval/priority data, not a generic "furthest behind" guess.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design,
including why the Grafana signal shapes (metrics vs. logs vs. traces) are
deliberately different from the obvious approach.

## Repo layout

```
pipeline/
  common/        shared telemetry (metrics/logs/traces) + Pub/Sub helpers + data model
  ingest/        HTTP entry point for new shots
  render/        comp/render stage (deliberately the slowest — backlog shows up here)
  color/         color/DI stage
  qc/            QC stage — randomly rejects back into render (rework loop)
  delivery/      terminal packaging stage
  scheduler/     source of truth for dependency/approval/priority/deadline metadata
  chaos/         deterministically triggers a backlog, for a repeatable demo
agent/           Gemini + ADK agent, connected to Grafana via MCP
infra/           deploy + Pub/Sub wiring scripts, Grafana alert rule skeleton
docs/            architecture writeup
```

## Track requirement checklist

- **Google Cloud AI**: agent runs on Gemini via `google-adk` (`agent/main.py`) — no other AI vendor anywhere in the stack.
- **Grafana at runtime**: the agent connects to the Grafana MCP server (`agent/main.py`, `MCPToolset`) and calls it live during the alert-investigate flow — not just referenced in docs.
- **Platform**: web (Cloud Run services + Grafana dashboard).
- **License**: MIT, see [`LICENSE`](LICENSE).

## Local development

```bash
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env   # fill in values

# run any single service locally, e.g.:
uvicorn pipeline.scheduler.main:app --reload --port 8081
uvicorn pipeline.ingest.main:app --reload --port 8082
```

Pub/Sub push delivery only works against deployed Cloud Run URLs (or the
Pub/Sub emulator) — for quick local iteration on one stage's logic, call its
`/pubsub/push` endpoint directly with a hand-built envelope instead of
standing up the whole chain.

## Deploying

```bash
export GCP_PROJECT_ID=...
export GCP_REGION=us-central1
export GRAFANA_OTLP_ENDPOINT=...
export GRAFANA_OTLP_TOKEN=...
export GRAFANA_STACK_URL=...
export GRAFANA_SERVICE_ACCOUNT_TOKEN=...

./infra/deploy.sh          # builds + deploys every Cloud Run service
./infra/pubsub_setup.sh    # creates topics + push subscriptions pointing at those services
```

Then in Grafana Cloud: build the dashboard + alert rule from
[`infra/grafana/alert_rule.json`](infra/grafana/alert_rule.json) (it's a
reference skeleton, not a working export — recreate it in the UI or via the
Grafana Terraform provider), pointing the alert webhook at
`https://shot-agent-<hash>.run.app/investigate`.

To rehearse the demo scenario on cue:

```bash
curl -X POST "https://shot-chaos-<hash>.run.app/inject-backlog?episode_id=ep04&shot_count=25"
```

## Status

The agent's code has been verified to actually build and import cleanly
(`docker build -f agent/Dockerfile .`, then running the container) — this
caught and fixed three real bugs in the ADK wiring, not just a docs read.
See "Resolved: ADK API surface" in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for what was wrong and what
changed.

This is still not a finished build, though. See "Known gaps / next steps" in
the same file for what's left: the Grafana dashboard/alert still need to be
built in the UI, chaos injector URLs are placeholders until the first
deploy, and nothing has been tested against a real, live Grafana Cloud stack
yet.
