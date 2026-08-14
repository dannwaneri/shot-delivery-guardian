# Architecture — Shot-Delivery Guardian

## Problem

Post-production studios run shot-based pipelines (ingest → comp/render →
color/DI → QC → package-for-delivery) against hard, contractual delivery
windows to streamers. When a stage backs up, someone has to manually dig
through dashboards to figure out whether a shot will miss its window, why,
and what to do about it. This project is an agent that does that
investigation automatically.

## 1. Simulated studio pipeline (data plane)

Cloud Run services connected by Pub/Sub, one topic per stage transition:

```
ingest --shot-render--> render --shot-color--> color --shot-qc--> qc --shot-delivery--> delivery
                            ^                                      |
                            +---------------- rework loop ---------+
                                 (QC rejects ~15% of shots)
```

A separate **scheduler** service is not a pipeline stage — it's the source
of truth for shot metadata (dependency graph, client-approval status,
priority tag, deadline) and is what makes the agent's bump recommendation
real instead of decorative (see §4).

A **chaos injector** service deterministically registers a burst of shots
fast enough to outrun render throughput, so the backlog/alert scenario is
reproducible on demand for a recording rather than left to chance.

## 2. What becomes a Grafana signal

This is the part that was actually load-bearing in design review — get it
wrong and either the free tier chokes on cardinality, or the agent has
nothing real to query.

| Signal | What's emitted | Cardinality shape |
|---|---|---|
| Metrics (Prometheus) | `render_queue_depth{stage}`, `stage_completions_total{stage}`, `stage_duration_seconds{stage,status}` | Labeled by **stage only** — bounded regardless of shot count. Never `shot_id` as a label. |
| Logs (Loki) | Structured JSON lines labeled by `service`, `episode_id`, `stage`, `status`; `shot_id`, `depends_on`, `client_approved`, `priority_tag`, `deadline` live inside the JSON body | Labels stay low-cardinality; shot identity is queried via LogQL's `\| json` filter, not an index label — Loki's index is label-based too, so promoting shot_id to a label would reproduce the same cardinality problem Prometheus has. |
| Traces (Tempo) | One trace per shot, `shot_id` and `episode_id` set as span attributes on every stage span | Tempo is built for high-cardinality, per-entity attribute search — this is the one place per-shot identity belongs natively. |

## 3. Alerting

A Grafana alert rule (see `infra/grafana/alert_rule.json`) computes
projected completion time from queue depth over recent throughput and
compares it to the deadline. When it fires, a webhook hits the agent's
`/investigate` endpoint.

## 4. Agent investigate loop

Gemini + ADK agent (`agent/main.py`), deployed on Cloud Run, connected to
Grafana via the Grafana MCP server:

1. Identify episode_id/shot_id from the alert payload.
2. Query Prometheus for queue depth + throughput at the affected stage →
   compute projected completion vs. deadline.
3. Query Tempo for the shot's trace → find which stage is actually consuming
   time (render backlog vs. stuck in a QC rework loop).
4. Query Loki for sibling shots in the episode → parse dependency/approval/
   priority metadata out of the JSON body.
5. Call `score_bump_candidates` (`agent/tools.py`) — a deterministic
   function, not LLM guesswork — to rank which shot is actually safe to
   deprioritize (not client-approved, no downstream dependents, not
   director-flagged, most slack to its own deadline).
6. Write a plain-English RCA + recommendation citing the tool's stated
   reasons.
7. Call the Grafana MCP annotation tool to post the finding onto the
   dashboard.

Steps 2–4 are genuine MCP queries against real signals emitted by the
pipeline; step 5 is genuinely computed from what those queries returned —
the design goal from the start was that a technically literate judge asking
"how did it decide to bump this shot over that one" gets a real answer, not
a narrated guess.

## 5. Demo reliability

Pipeline timing is inherently random; the chaos injector exists specifically
so the backlog/alert/investigate sequence can be triggered on cue during a
3-minute recording instead of hoped for.

## Known gaps / next steps

- Grafana dashboard + alert rule are currently a JSON skeleton
  (`infra/grafana/alert_rule.json`) — needs to be built in the Grafana Cloud
  UI and exported back, or defined via the Grafana Terraform provider.
- Scheduler service state is in-memory; fine for a demo, would need Firestore
  for anything that has to survive a restart.
- `pipeline/chaos/main.py` has placeholder service URLs that need to be
  replaced (or read from env vars) after the first `infra/deploy.sh` run.
- No real Grafana Cloud stack has been connected yet — everything below is
  verified at the *code* level (imports resolve, container builds and runs),
  not against a live Grafana instance yet. That's the next real test.

### Resolved: `agent/main.py`'s ADK API surface

This was flagged as unverified; it has since been checked by actually
building `agent/Dockerfile` and running the import chain in the container,
not just reading docs. Three real bugs were found and fixed:

1. `MCPToolset` is a deprecated alias — the current class is `McpToolset`,
   exported from `google.adk.tools` (not `google.adk.tools.mcp_tool`, whose
   `__init__.py` silently swallows an unrelated import failure — see #2).
2. `google-adk`'s MCP support needs the `[mcp]` extra
   (`google-adk[mcp]==2.7.0`) — plain `google-adk` does not install the
   `mcp` PyPI package that `McpToolset` depends on.
3. `StdioServerParameters` comes from the separate `mcp` package, not
   google-adk, and should be wrapped in `StdioConnectionParams` (the
   currently-recommended form — using it bare works but prints a
   deprecation-style warning).

Also found and fixed in the same pass: `mcp-grafana` itself isn't a Python
package, so it needed a Go build stage in `agent/Dockerfile`
(`GOTOOLCHAIN=auto`, since the base image's Go was older than what
`mcp-grafana`'s go.mod requires), and the original pinned
`fastapi`/`uvicorn` versions conflicted with what `google-adk` requires —
resolved by letting `google-adk` own that resolution instead of pinning
separately.
