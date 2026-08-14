"""
Deterministic bump-scoring tool.

This is intentionally NOT left to free-form LLM reasoning: the agent gathers
candidate shots from Grafana (Loki query results, passed in as plain dicts),
and this function applies the agreed rule so the recommendation is
reproducible and defensible — not vibes dressed up in industry vocabulary.

Rule (highest priority to bump/deprioritize first):
  1. NOT client_approved (approved shots are locked, never bumped)
  2. AND no downstream dependents (nothing else in the episode depends on it)
  3. AND not director_flagged (protected priority)
  4. Among what's left, most slack (furthest from its own deadline) first
"""
from __future__ import annotations

from datetime import datetime


def score_bump_candidates(shots: list[dict], now_iso: str | None = None) -> dict:
    """
    Args:
        shots: shot metadata dicts pulled from Loki, each with shot_id,
            depends_on (list[str]), client_approved (bool), priority_tag (str),
            deadline (ISO 8601 str).
        now_iso: override for "current time" (defaults to utcnow); useful for
            deterministic testing.

    Returns:
        {"ranked": [...]} — shots ordered most-to-least eligible to bump,
        each annotated with the reasons behind its ranking.
    """
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.utcnow()
    depended_on = {dep for s in shots for dep in s.get("depends_on", [])}

    def slack_hours(shot: dict) -> float:
        deadline = datetime.fromisoformat(shot["deadline"])
        return (deadline - now).total_seconds() / 3600

    ranked = []
    for shot in shots:
        has_dependents = shot["shot_id"] in depended_on
        reasons: list[str] = []
        eligible = True

        if shot.get("client_approved"):
            eligible = False
            reasons.append("client-approved: locked, do not bump")
        if has_dependents:
            eligible = False
            reasons.append("blocks downstream shot(s): bumping cascades the delay")
        if shot.get("priority_tag") == "director_flagged":
            eligible = False
            reasons.append("director-flagged: protected priority")

        if eligible:
            reasons.append(f"{slack_hours(shot):.1f}h slack to its own deadline")

        ranked.append(
            {
                "shot_id": shot["shot_id"],
                "eligible_to_bump": eligible,
                "slack_hours": round(slack_hours(shot), 2),
                "reasons": reasons,
            }
        )

    ranked.sort(key=lambda r: (not r["eligible_to_bump"], -r["slack_hours"]))
    return {"ranked": ranked}
