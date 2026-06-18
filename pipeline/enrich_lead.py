"""GT-3: Lead Enricher — 1 async LLM call per lead (Call A)."""

from __future__ import annotations

import json
from typing import Any

import anthropic

from pipeline.derive_schema import EnrichmentFieldDef
from pipeline.synthesize_business import BusinessProfile


def _build_enrich_tool(field_defs: list[EnrichmentFieldDef]) -> dict:
    """
    Dynamically construct the Anthropic tool schema from field_defs.
    Each boolean field_def → boolean property.
    Each string field_def → string property.
    Always adds 'summary' string property.
    """
    properties: dict[str, Any] = {}

    for field in field_defs:
        if field["type"] == "boolean":
            properties[field["key"]] = {
                "type": "boolean",
                "description": field["question"],
            }
        else:
            properties[field["key"]] = {
                "type": "string",
                "description": field["question"],
            }

    # Always add summary
    properties["summary"] = {
        "type": "string",
        "description": (
            "Rich paragraph: who is this lead, what do they want, notable signals from "
            "posts/DM, why they do or don't fit the business."
        ),
    }

    return {
        "name": "enrich_lead",
        "description": "Enrich a lead with structured fields derived from their profile and DM.",
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties.keys()),
        },
    }


def _build_enrich_prompt(
    lead: dict,
    business_profile: BusinessProfile,
    field_defs: list[EnrichmentFieldDef],
) -> str:
    spam_signals = "\n".join(f"  - {s}" for s in business_profile.get("spamSignals", []))
    field_instructions = "\n".join(
        f"  - {f['key']} ({f['type']}): {f['question']}" for f in field_defs
    )

    return (
        f"You are analyzing an Instagram DM lead for the business: {business_profile['name']}.\n\n"
        f"Business description: {business_profile['description']}\n"
        f"Ideal customer: {business_profile['icp']}\n\n"
        f"Spam signals to watch for:\n{spam_signals}\n\n"
        f"Lead profile:\n{json.dumps(lead, indent=2)}\n\n"
        f"Evaluate this lead on the following fields:\n{field_instructions}\n\n"
        "Also write a rich summary paragraph covering: who this lead is, what they want, "
        "notable signals from their posts and DM, and why they do or don't fit the business.\n\n"
        "Call the enrich_lead tool with your analysis."
    )


async def enrich_lead(
    lead: dict,
    business_profile: BusinessProfile,
    field_defs: list[EnrichmentFieldDef],
    client: anthropic.AsyncAnthropic,
) -> dict[str, Any]:
    """
    Enrich one lead via 1 async Anthropic API call (Call A).
    Returns dict with all field keys + 'summary'.
    Raises RuntimeError on API failure.
    """
    tool_def = _build_enrich_tool(field_defs)
    prompt = _build_enrich_prompt(lead, business_profile, field_defs)

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            tools=[tool_def],
            tool_choice={"type": "tool", "name": "enrich_lead"},
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        raise RuntimeError(
            f"Anthropic API call failed in enrich_lead for {lead.get('username', '?')}: {exc}"
        ) from exc

    tool_block = next(
        (block for block in response.content if block.type == "tool_use"),
        None,
    )
    if tool_block is None:
        raise RuntimeError(
            f"No tool_use block in enrich_lead response for {lead.get('username', '?')}."
        )

    return dict(tool_block.input)  # type: ignore[arg-type]
