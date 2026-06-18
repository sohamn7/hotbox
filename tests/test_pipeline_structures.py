"""
Structural contracts for GT-1, GT-3, GT-4.
All Anthropic API calls are mocked — no real network traffic.
"""

import json
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline.synthesize_business import synthesize_business, BusinessProfile
from pipeline.enrich_lead import enrich_lead
from pipeline.score_lead import score_lead
from pipeline.derive_schema import derive_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tool_response(input_data: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.input = input_data
    response = MagicMock()
    response.content = [block]
    return response


def _async_tool_response(input_data: dict) -> AsyncMock:
    block = MagicMock()
    block.type = "tool_use"
    block.input = input_data
    response = MagicMock()
    response.content = [block]
    mock_create = AsyncMock(return_value=response)
    return mock_create


_SAMPLE_PROFILE: BusinessProfile = {
    "goals": [{"label": "coaching signups", "priority": 1}],
    "icp": "gym-goers 20s-40s",
    "spamSignals": ["generic compliment"],
    "name": "Test Co",
    "description": "A fitness brand",
}


# ---------------------------------------------------------------------------
# GT-1: synthesize_business
# ---------------------------------------------------------------------------

def test_synthesize_business_output_has_required_keys():
    profile_data = {
        "goals": [{"label": "coaching signups", "priority": 1}],
        "icp": "gym-goers",
        "spamSignals": ["generic compliment"],
        "name": "Test Co",
        "description": "A fitness brand",
    }
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump({"name": "Test Co"}, f)
        tmp = f.name

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_response(profile_data)

    with patch("pipeline.synthesize_business.anthropic.Anthropic", return_value=mock_client):
        result = synthesize_business(tmp)

    for key in ("goals", "icp", "spamSignals", "name", "description"):
        assert key in result, f"Missing key: {key}"


def test_synthesize_business_goals_sorted_by_priority():
    profile_data = {
        "goals": [
            {"label": "product sales", "priority": 2},
            {"label": "coaching signups", "priority": 1},
        ],
        "icp": "gym-goers",
        "spamSignals": [],
        "name": "Test Co",
        "description": "desc",
    }
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump({}, f)
        tmp = f.name

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_response(profile_data)

    with patch("pipeline.synthesize_business.anthropic.Anthropic", return_value=mock_client):
        result = synthesize_business(tmp)

    priorities = [g["priority"] for g in result["goals"]]
    assert priorities == sorted(priorities)


def test_synthesize_business_raises_on_missing_file():
    with pytest.raises(RuntimeError, match="Failed to read business JSON"):
        synthesize_business("/nonexistent/path/business.json")


# ---------------------------------------------------------------------------
# GT-3: enrich_lead
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enrich_lead_returns_all_field_keys_and_summary():
    field_defs = [
        {"key": "wantsCoaching", "question": "Wants coaching?", "type": "boolean"},
        {"key": "isSpam", "question": "Is spam?", "type": "boolean"},
        {"key": "fitnessRelevance", "question": "Fitness relevance?", "type": "string"},
    ]
    enrichment_data = {
        "wantsCoaching": True,
        "isSpam": False,
        "fitnessRelevance": "high — active lifter",
        "summary": "Matt is a dedicated lifter seeking structured coaching.",
    }

    mock_client = AsyncMock()
    mock_client.messages.create.return_value = _tool_response(enrichment_data)

    lead = {"username": "matt.lifts", "fullName": "Matt R.", "bio": "lifter", "dm": "need coaching"}
    result = await enrich_lead(lead, _SAMPLE_PROFILE, field_defs, mock_client)

    for field in field_defs:
        assert field["key"] in result, f"Missing enrichment key: {field['key']}"
    assert "summary" in result
    assert isinstance(result["summary"], str)
    assert len(result["summary"]) > 0


@pytest.mark.asyncio
async def test_enrich_lead_boolean_fields_are_bool():
    field_defs = [
        {"key": "wantsCoaching", "question": "Wants coaching?", "type": "boolean"},
        {"key": "isSpam", "question": "Is spam?", "type": "boolean"},
        {"key": "fitnessRelevance", "question": "Relevance?", "type": "string"},
    ]
    enrichment_data = {
        "wantsCoaching": True,
        "isSpam": False,
        "fitnessRelevance": "high",
        "summary": "A summary.",
    }

    mock_client = AsyncMock()
    mock_client.messages.create.return_value = _tool_response(enrichment_data)

    lead = {"username": "test_user"}
    result = await enrich_lead(lead, _SAMPLE_PROFILE, field_defs, mock_client)

    assert isinstance(result["wantsCoaching"], bool)
    assert isinstance(result["isSpam"], bool)


# ---------------------------------------------------------------------------
# GT-4: score_lead
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_lead_returns_qualityScore_int():
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = _tool_response({"qualityScore": 82})

    enrichment = {"wantsCoaching": True, "isSpam": False, "summary": "High-intent lead."}
    result = await score_lead(enrichment, _SAMPLE_PROFILE, mock_client)

    assert "qualityScore" in result
    assert isinstance(result["qualityScore"], int)


@pytest.mark.asyncio
async def test_score_lead_clamped_to_0_100():
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = _tool_response({"qualityScore": 150})

    enrichment = {"isSpam": False, "summary": "Test"}
    result = await score_lead(enrichment, _SAMPLE_PROFILE, mock_client)

    assert 0 <= result["qualityScore"] <= 100


@pytest.mark.asyncio
async def test_score_lead_spam_clamped_to_zero():
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = _tool_response({"qualityScore": -999})

    enrichment = {"isSpam": True, "summary": "Spam"}
    result = await score_lead(enrichment, _SAMPLE_PROFILE, mock_client)

    assert result["qualityScore"] == 0
