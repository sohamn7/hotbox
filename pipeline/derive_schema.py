"""GT-2: Schema Deriver — deterministic, no LLM call."""

from __future__ import annotations

import re
from typing import Literal, TypedDict

from pipeline.synthesize_business import BusinessProfile


class EnrichmentFieldDef(TypedDict):
    key: str
    question: str
    type: Literal["boolean", "string"]


def _sanitize_key(raw_key: str) -> str:
    """Ensure LLM-generated key is valid camelCase with no spaces or special chars."""
    clean = re.sub(r"[^a-zA-Z0-9]", " ", raw_key).split()
    if not clean:
        return "goal"
    return clean[0][0].lower() + clean[0][1:] + "".join(w.capitalize() for w in clean[1:])


def derive_schema(business_profile: BusinessProfile) -> list[EnrichmentFieldDef]:
    """
    Build enrichment field definitions from the business profile.
    One boolean per goal (using LLM-generated key) + isSpam boolean + domainRelevance string.
    Deterministic — no LLM calls.
    """
    fields: list[EnrichmentFieldDef] = []
    seen_keys: set[str] = set()

    for goal in business_profile["goals"]:
        label = goal["label"]
        raw_key = goal.get("key", label)
        base = _sanitize_key(raw_key)
        key = f"wants{base[0].upper()}{base[1:]}"

        # Deduplicate if two goals produce the same key
        original_key = key
        suffix = 2
        while key in seen_keys:
            key = f"{original_key}{suffix}"
            suffix += 1
        seen_keys.add(key)

        fields.append(
            EnrichmentFieldDef(
                key=key,
                question=(
                    f"The key '{key}' means the lead wants {label}. "
                    f"Is this lead's intent genuinely aligned with '{label}'? (true/false)"
                ),
                type="boolean",
            )
        )

    # Always append isSpam
    fields.append(
        EnrichmentFieldDef(
            key="isSpam",
            question="Is this message spam or irrelevant to the business?",
            type="boolean",
        )
    )

    # Always append domainRelevance — generic across any business type
    fields.append(
        EnrichmentFieldDef(
            key="domainRelevance",
            question=(
                "How relevant is this lead to the business's domain and ideal customer profile? "
                "(high/medium/low + one-sentence reason)"
            ),
            type="string",
        )
    )

    return fields


if __name__ == "__main__":
    import json
    from pipeline.synthesize_business import synthesize_business

    profile = synthesize_business("data/business.json")
    schema = derive_schema(profile)
    print(json.dumps(schema, indent=2))
