"""GT-4: Lead Scorer — 1 async LLM call per lead (Call B)."""

from __future__ import annotations

import json
from typing import Any

import anthropic

from pipeline.synthesize_business import BusinessProfile

_SCORE_TOOL: dict = {
    "name": "score_lead",
    "description": "Return a quality score (0–100) for a lead based on enrichment data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "qualityScore": {
                "type": "integer",
                "description": "Lead quality score from 0 to 100.",
                "minimum": 0,
                "maximum": 100,
            }
        },
        "required": ["qualityScore"],
    },
}


def _compute_goal_weights(goals: list[dict]) -> list[tuple[str, int]]:
    """
    Assign explicit point values to each goal using exponential decay.
    Total pool = 40 pts. Priority 1 always gets the largest share.
    Returns list of (goal_label, points) sorted by priority.
    """
    n = len(goals)
    if n == 0:
        return []
    # Raw weights: 4, 2, 1, 0.5... (each half of the previous)
    raw = [4 / (2 ** i) for i in range(n)]
    total = sum(raw)
    # Normalize to sum to 40, round to integers
    weights = [max(1, round(w * 40 / total)) for w in raw]
    sorted_goals = sorted(goals, key=lambda g: g["priority"])
    return [(g["label"], w) for g, w in zip(sorted_goals, weights)]


def _build_score_prompt(
    enrichment: dict[str, Any],
    business_profile: BusinessProfile,
) -> str:
    goal_weights = _compute_goal_weights(business_profile["goals"])

    goal_lines = "\n".join(
        f"  - '{label}' match: up to {pts} pts  "
        f"({'HIGHEST priority — most impactful' if i == 0 else f'priority {i+1}'})"
        for i, (label, pts) in enumerate(goal_weights)
    )
    total_goal_pts = sum(pts for _, pts in goal_weights)

    return (
        f"You are scoring an Instagram lead for the business: {business_profile['name']}.\n\n"
        f"Ideal customer profile: {business_profile['icp']}\n\n"
        f"Lead enrichment data:\n{json.dumps(enrichment, indent=2)}\n\n"
        "Score this lead 0–100 using this exact rubric (additive, floor at 0):\n\n"
        f"  GOAL ALIGNMENT ({total_goal_pts} pts total — award per matched goal):\n"
        f"{goal_lines}\n\n"
        f"  ICP MATCH (30 pts): Does the lead match this ideal customer profile?\n"
        f"    \"{business_profile['icp']}\"\n"
        f"    Score 0–30 based on how closely the lead fits this description.\n\n"
        "  DM QUALITY (20 pts): Is the DM specific, genuine, and high-intent?\n"
        "    - Generic/copy-paste = 0–5 pts. Specific, personal ask = 15–20 pts\n\n"
        "  ENGAGEMENT AUTHENTICITY (10 pts): Are their posts/follower counts real?\n"
        "    - Suspicious ratios or fake-looking content = 0–2 pts\n\n"
        "  SPAM PENALTY: if isSpam is true, subtract 60 pts (minimum final score: 0)\n\n"
        "IMPORTANT: Goal alignment scores are NOT interchangeable. A lead matching only "
        "the highest-priority goal should outscore a lead matching only lower-priority goals "
        "by a wide margin, even if the lower-priority lead has better engagement.\n\n"
        "Call the score_lead tool with your final integer score."
    )


async def score_lead(
    enrichment: dict[str, Any],
    business_profile: BusinessProfile,
    client: anthropic.AsyncAnthropic,
) -> dict[str, int]:
    """
    Score one lead via 1 async Anthropic API call (Call B).
    Returns {'qualityScore': int}.
    Raises RuntimeError on API failure.
    """
    prompt = _build_score_prompt(enrichment, business_profile)

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            tools=[_SCORE_TOOL],
            tool_choice={"type": "tool", "name": "score_lead"},
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        raise RuntimeError(f"Anthropic API call failed in score_lead: {exc}") from exc

    tool_block = next(
        (block for block in response.content if block.type == "tool_use"),
        None,
    )
    if tool_block is None:
        raise RuntimeError("No tool_use block in score_lead response.")

    raw: dict = dict(tool_block.input)  # type: ignore[arg-type]
    score = int(raw.get("qualityScore", 0))
    # Clamp to [0, 100] as a defensive measure
    score = max(0, min(100, score))
    return {"qualityScore": score}
