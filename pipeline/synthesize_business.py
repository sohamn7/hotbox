"""GT-1: Business Synthesizer — 1 LLM call, structured output via tool use."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

import anthropic


class GoalDef(TypedDict):
    label: str
    priority: int


class BusinessProfile(TypedDict):
    goals: list[GoalDef]
    icp: str
    spamSignals: list[str]
    name: str
    description: str


_TOOL_DEF: dict = {
    "name": "set_business_profile",
    "description": "Store the structured business profile extracted from the raw business JSON.",
    "input_schema": {
        "type": "object",
        "properties": {
            "goals": {
                "type": "array",
                "description": "Business goals sorted by priority (1 = highest).",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "description": "Short label for the goal."},
                        "priority": {"type": "integer", "description": "Priority rank, 1 = most important."},
                        "key": {
                            "type": "string",
                            "description": (
                                "A 1-2 word camelCase identifier for this goal's main subject — "
                                "NO 'wants' prefix (that is added automatically). "
                                "Pick the clearest, most specific noun(s) that name what the lead wants. "
                                "Examples: 'coaching', 'installation', 'retailProduct', 'designCollab', 'productSales'. "
                                "Avoid vague action verbs like 'secure', 'generate', 'pursue', 'increase'."
                            ),
                        },
                    },
                    "required": ["label", "priority", "key"],
                },
            },
            "icp": {
                "type": "string",
                "description": "Concise ideal customer profile description.",
            },
            "spamSignals": {
                "type": "array",
                "description": "List of signals that indicate a DM is spam or irrelevant.",
                "items": {"type": "string"},
            },
            "name": {
                "type": "string",
                "description": "Business name.",
            },
            "description": {
                "type": "string",
                "description": "Short description of the business.",
            },
        },
        "required": ["goals", "icp", "spamSignals", "name", "description"],
    },
}


def synthesize_business(business_json_path: str | Path) -> BusinessProfile:
    """
    Reads raw business.json and returns a structured BusinessProfile.
    Makes exactly 1 Anthropic LLM call using tool use.
    Raises on any I/O or API failure.
    """
    path = Path(business_json_path)
    try:
        raw = path.read_text(encoding="utf-8")
        business_data: dict = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to read business JSON at {path}: {exc}") from exc

    client = anthropic.Anthropic()

    prompt = (
        "You are a business analyst. Read this business profile and extract a structured summary.\n\n"
        f"Business profile (raw):\n{json.dumps(business_data, indent=2)}\n\n"
        "Extract:\n"
        "- goals: list of business goals, sorted by priority (1 = most important), each with a short label\n"
        "- icp: concise ideal customer profile in one sentence\n"
        "- spamSignals: list of signals from 'commonSpam' that indicate irrelevant/spam DMs\n"
        "- name: business name\n"
        "- description: short description of what the business does\n\n"
        "Call the set_business_profile tool with your analysis."
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            tools=[_TOOL_DEF],
            tool_choice={"type": "tool", "name": "set_business_profile"},
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        raise RuntimeError(f"Anthropic API call failed in synthesize_business: {exc}") from exc

    # Extract tool use block
    tool_block = next(
        (block for block in response.content if block.type == "tool_use"),
        None,
    )
    if tool_block is None:
        raise RuntimeError("No tool_use block in synthesize_business response.")

    profile: BusinessProfile = tool_block.input  # type: ignore[assignment]

    # Sort goals by priority to guarantee order
    profile["goals"] = sorted(profile["goals"], key=lambda g: g["priority"])

    return profile


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "data/business.json"
    result = synthesize_business(path)
    print(json.dumps(result, indent=2))
