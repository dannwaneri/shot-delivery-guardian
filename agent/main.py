"""
Shot-Delivery Guardian agent.

Investigate loop (see docs/ARCHITECTURE.md for the full design rationale):
  1. Identify episode_id/shot_id from the incoming Grafana alert webhook.
  2. Query Prometheus (via Grafana MCP) for render_queue_depth and
     stage_completions_total at the affected stage -> project completion
     time and compare it against the shot's deadline.
  3. Query Tempo for the at-risk shot's trace (filtered by the shot_id span
     attribute) -> find which stage is actually consuming the time.
  4. Query Loki for sibling shots in the same episode -> parse the JSON body
     for depends_on / client_approved / priority_tag / deadline (these are
     body fields, not labels — see pipeline.common.telemetry).
  5. Call score_bump_candidates with the shots from step 4 -> a real
     computation, not an LLM guess dressed up as one.
  6. Write a plain-English RCA + recommendation citing the tool's reasons.
  7. Call the Grafana MCP annotation tool to post the finding onto the
     relevant dashboard.

NOTE on the ADK API surface: verified against the real, installed
google-adk==2.7.0 package (not docs alone) by running the import chain
inside the built container. Two real findings from that check:
  - `MCPToolset` is a deprecated alias; the current class is `McpToolset`,
    exported from `google.adk.tools` (top-level). Importing from
    `google.adk.tools.mcp_tool` directly fails, because that submodule's
    __init__.py wraps its exports in a try/except that silently swallows an
    unrelated ImportError if the `mcp` package isn't installed.
  - `StdioServerParameters` is not a google-adk class at all — it comes from
    the separate `mcp` PyPI package (the official MCP SDK), which google-adk
    only installs if you request the `[mcp]` extra (see agent/requirements.txt).
Re-run this same check after any `pip install -U google-adk` — this library
moves fast enough that this could drift again.

The MCP connection here targets the open-source grafana-mcp server with a
service-account token rather than the hosted OAuth endpoint at
mcp.grafana.com, because this agent runs unattended (triggered by an alert
webhook, no human present to complete a browser OAuth flow) — see the
Grafana track resources' note on unattended deployments. The `mcp-grafana`
binary itself, its `-t stdio` flag, and the GRAFANA_URL /
GRAFANA_SERVICE_ACCOUNT_TOKEN env var names are confirmed against the
official github.com/grafana/mcp-grafana README — that part is verified, not
guessed. See agent/Dockerfile for how the binary gets built in.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Request
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool, McpToolset
from google.adk.tools.mcp_tool import StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters

from agent.tools import score_bump_candidates

GRAFANA_MCP_TOKEN = os.environ["GRAFANA_SERVICE_ACCOUNT_TOKEN"]
GRAFANA_STACK_URL = os.environ["GRAFANA_STACK_URL"]

grafana_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="mcp-grafana",
            args=["-t", "stdio"],
            env={
                "GRAFANA_URL": GRAFANA_STACK_URL,
                "GRAFANA_SERVICE_ACCOUNT_TOKEN": GRAFANA_MCP_TOKEN,
            },
        ),
        timeout=10.0,
    )
)

bump_scoring_tool = FunctionTool(score_bump_candidates)

guardian_agent = Agent(
    name="shot_delivery_guardian",
    model="gemini-2.5-flash",
    instruction="""
You are the Shot-Delivery Guardian for a post-production studio's Grafana
Cloud stack. When you receive an alert about a shot at risk of missing its
delivery window, follow this exact sequence and do not skip steps:

1. Identify the episode_id and shot_id from the alert payload.
2. Query Prometheus for render_queue_depth and stage_completions_total at the
   affected stage. Compute projected completion time from queue depth over
   recent throughput, and compare it to the shot's deadline.
3. Query Tempo for the shot's trace (filter by the shot_id span attribute) to
   identify which stage is actually consuming the time.
4. Query Loki for all shots in the same episode (filter on the episode_id
   label, then parse the JSON body for shot_id, depends_on, client_approved,
   priority_tag, deadline).
5. Call score_bump_candidates with the shots you retrieved in step 4. Do not
   invent a ranking yourself - use the tool's output as-is.
6. Write a short root-cause summary and a specific recommendation, citing the
   tool's stated reasons, not just its ranking.
7. Call the Grafana annotation tool to post your summary onto the relevant
   dashboard, tagged with the episode_id.

Be concrete: name shot IDs, stages, and hours of slack. Never say "some
shots" or "a delay was detected" without the numbers behind it.
""",
    tools=[grafana_toolset, bump_scoring_tool],
)

session_service = InMemorySessionService()
runner = Runner(agent=guardian_agent, session_service=session_service, app_name="shot_delivery_guardian")

app = FastAPI()


@app.post("/investigate")
async def investigate(request: Request):
    """Grafana alert webhook target."""
    alert = await request.json()
    session = await session_service.create_session(
        user_id="grafana_alert",
        app_name="shot_delivery_guardian"
    )
    prompt_text = f"Alert fired: {alert}. Investigate and post your finding."
    new_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt_text)]
    )
    events = []
    async for event in runner.run_async(
        user_id="grafana_alert",
        session_id=session.id,
        new_message=new_message
    ):
        events.append(event)

    response_texts = []
    for event in events:
        if getattr(event, "content", None) and getattr(event.content, "parts", None):
            for part in event.content.parts:
                if getattr(part, "text", None):
                    response_texts.append(part.text)

    final_output = "\n\n".join(response_texts) if response_texts else "Investigation completed."
    return {
        "status": "investigated",
        "recommendation": final_output,
        "events_count": len(events)
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
