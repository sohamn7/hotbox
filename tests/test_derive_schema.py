"""GT-2 unit tests — pure, deterministic, no mocking needed."""

import pytest
from pipeline.synthesize_business import BusinessProfile
from pipeline.derive_schema import derive_schema


def _make_profile(goal_labels: list[str]) -> BusinessProfile:
    return BusinessProfile(
        goals=[{"label": l, "priority": i + 1} for i, l in enumerate(goal_labels)],
        icp="gym-goers",
        spamSignals=["generic compliment"],
        name="Test Co",
        description="A test company",
    )


def test_field_count_equals_goals_plus_two():
    """N goals → N boolean fields + isSpam + fitnessRelevance."""
    for n in [1, 2, 3]:
        profile = _make_profile([f"goal {i}" for i in range(n)])
        fields = derive_schema(profile)
        assert len(fields) == n + 2


def test_isSpam_always_present():
    profile = _make_profile(["coaching signups"])
    keys = [f["key"] for f in derive_schema(profile)]
    assert "isSpam" in keys


def test_fitnessRelevance_always_present_and_string():
    profile = _make_profile(["coaching signups"])
    fields = derive_schema(profile)
    fr = next(f for f in fields if f["key"] == "fitnessRelevance")
    assert fr["type"] == "string"


def test_goal_fields_are_boolean():
    profile = _make_profile(["coaching signups", "product sales"])
    fields = derive_schema(profile)
    goal_fields = [f for f in fields if f["key"] not in ("isSpam", "fitnessRelevance")]
    assert all(f["type"] == "boolean" for f in goal_fields)


def test_goal_keys_start_with_wants():
    profile = _make_profile(["coaching signups", "product sales"])
    fields = derive_schema(profile)
    goal_fields = [f for f in fields if f["key"] not in ("isSpam", "fitnessRelevance")]
    assert all(f["key"].startswith("wants") for f in goal_fields)


def test_duplicate_goal_labels_produce_unique_keys():
    """Two goals that map to the same camelCase key must be deduplicated."""
    profile = _make_profile(["coaching signups", "coaching bootcamps"])
    fields = derive_schema(profile)
    goal_keys = [f["key"] for f in fields if f["key"] not in ("isSpam", "fitnessRelevance")]
    assert len(goal_keys) == len(set(goal_keys))


def test_each_field_has_required_keys():
    profile = _make_profile(["coaching signups"])
    for field in derive_schema(profile):
        assert "key" in field
        assert "question" in field
        assert "type" in field
        assert field["type"] in ("boolean", "string")


def test_empty_goals_still_has_isSpam_and_fitnessRelevance():
    profile = _make_profile([])
    fields = derive_schema(profile)
    keys = [f["key"] for f in fields]
    assert "isSpam" in keys
    assert "fitnessRelevance" in keys
    assert len(fields) == 2
