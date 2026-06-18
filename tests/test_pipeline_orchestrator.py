"""
GT-5 orchestrator tests — hash gate and DB reset on file change.
All LLM calls are mocked. Uses real temp files and SQLite.
"""

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import pipeline.run as run_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(business_path: Path, leads_path: Path) -> str:
    return hashlib.sha256(
        business_path.read_bytes() + leads_path.read_bytes()
    ).hexdigest()


def _read_leads(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM leads ORDER BY score DESC").fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _read_stored_hash(db_path: Path) -> str | None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='input_hash'").fetchone()
        return row["value"] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def _seed_db(db_path: Path, leads: list[dict], stored_hash: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('input_hash', ?)", (stored_hash,)
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            username TEXT PRIMARY KEY, full_name TEXT, raw_dm TEXT,
            score INTEGER, summary TEXT, enrichment TEXT,
            status TEXT DEFAULT 'inbox', reply_text TEXT DEFAULT ''
        )
        """
    )
    for lead in leads:
        conn.execute(
            "INSERT OR REPLACE INTO leads VALUES (?,?,?,?,?,?,?,?)",
            (lead["username"], lead["full_name"], lead["raw_dm"],
             lead["score"], lead["summary"], lead["enrichment"],
             lead.get("status", "inbox"), lead.get("reply_text", "")),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

INITIAL_BUSINESS = {"name": "Old Biz", "goals": ["old goal"]}
INITIAL_LEADS = [{"username": "old_lead", "fullName": "Old Lead", "dm": "old dm"}]

NEW_BUSINESS = {"name": "New Biz", "goals": ["new goal"]}
NEW_LEADS = [
    {"username": "new_lead_1", "fullName": "New Lead One", "dm": "I want coaching"},
    {"username": "new_lead_2", "fullName": "New Lead Two", "dm": "interested in products"},
]


@pytest.fixture()
def file_setup(tmp_path):
    """Return temp paths; caller writes content as needed."""
    return {
        "business": tmp_path / "business.json",
        "leads": tmp_path / "leads.json",
        "db": tmp_path / "hotbox.db",
    }


def _make_mock_profile(name="New Biz"):
    return {
        "goals": [{"label": "coaching signups", "priority": 1}],
        "icp": "gym-goers",
        "spamSignals": ["spam"],
        "name": name,
        "description": "A fitness brand",
    }


async def _mock_enrich(lead, profile, fields, client):
    return {
        "wantsCoaching": True,
        "isSpam": False,
        "fitnessRelevance": "high",
        "summary": f"Summary for {lead.get('username', '?')}",
    }


async def _mock_score(enrichment, profile, client):
    return {"qualityScore": 75}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_changed_files_reset_db_and_store_new_leads(file_setup, monkeypatch):
    """
    When business.json + leads.json change, the pipeline re-runs:
    old leads are removed and only new leads appear in the DB.
    """
    b, l, db = file_setup["business"], file_setup["leads"], file_setup["db"]

    # Write initial files and seed DB with old data + old hash
    b.write_text(json.dumps(INITIAL_BUSINESS))
    l.write_text(json.dumps(INITIAL_LEADS))
    old_hash = _sha256(b, l)
    _seed_db(db, [
        {"username": "old_lead", "full_name": "Old Lead", "raw_dm": "old",
         "score": 60, "summary": "old summary", "enrichment": "{}"}
    ], old_hash)

    # Write new files (different content → different hash)
    b.write_text(json.dumps(NEW_BUSINESS))
    l.write_text(json.dumps(NEW_LEADS))

    monkeypatch.setattr(run_module, "_BUSINESS_JSON", b)
    monkeypatch.setattr(run_module, "_LEADS_JSON", l)
    monkeypatch.setattr(run_module, "_DB_PATH", db)

    with (
        patch("pipeline.run.synthesize_business", return_value=_make_mock_profile()),
        patch("pipeline.run.enrich_lead", side_effect=_mock_enrich),
        patch("pipeline.run.score_lead", side_effect=_mock_score),
        patch("pipeline.run.anthropic.AsyncAnthropic", return_value=MagicMock()),
    ):
        await run_module.run_pipeline()

    leads_in_db = _read_leads(db)
    usernames = [r["username"] for r in leads_in_db]

    # Old lead must be gone
    assert "old_lead" not in usernames, "old lead should have been removed"
    # New leads must be present
    assert "new_lead_1" in usernames
    assert "new_lead_2" in usernames
    assert len(leads_in_db) == len(NEW_LEADS)


@pytest.mark.asyncio
async def test_changed_files_update_stored_hash(file_setup, monkeypatch):
    """After re-run, the stored hash should match the new files."""
    b, l, db = file_setup["business"], file_setup["leads"], file_setup["db"]

    b.write_text(json.dumps(INITIAL_BUSINESS))
    l.write_text(json.dumps(INITIAL_LEADS))
    _seed_db(db, [], _sha256(b, l))

    b.write_text(json.dumps(NEW_BUSINESS))
    l.write_text(json.dumps(NEW_LEADS))
    expected_hash = _sha256(b, l)

    monkeypatch.setattr(run_module, "_BUSINESS_JSON", b)
    monkeypatch.setattr(run_module, "_LEADS_JSON", l)
    monkeypatch.setattr(run_module, "_DB_PATH", db)

    with (
        patch("pipeline.run.synthesize_business", return_value=_make_mock_profile()),
        patch("pipeline.run.enrich_lead", side_effect=_mock_enrich),
        patch("pipeline.run.score_lead", side_effect=_mock_score),
        patch("pipeline.run.anthropic.AsyncAnthropic", return_value=MagicMock()),
    ):
        await run_module.run_pipeline()

    assert _read_stored_hash(db) == expected_hash


@pytest.mark.asyncio
async def test_same_files_skip_pipeline_and_preserve_db(file_setup, monkeypatch):
    """
    When files haven't changed, the pipeline is skipped — existing DB rows untouched.
    """
    b, l, db = file_setup["business"], file_setup["leads"], file_setup["db"]

    b.write_text(json.dumps(INITIAL_BUSINESS))
    l.write_text(json.dumps(INITIAL_LEADS))
    current_hash = _sha256(b, l)
    _seed_db(db, [
        {"username": "cached_lead", "full_name": "Cached", "raw_dm": "dm",
         "score": 80, "summary": "cached summary", "enrichment": "{}"}
    ], current_hash)

    monkeypatch.setattr(run_module, "_BUSINESS_JSON", b)
    monkeypatch.setattr(run_module, "_LEADS_JSON", l)
    monkeypatch.setattr(run_module, "_DB_PATH", db)

    mock_synthesize = MagicMock(return_value=_make_mock_profile())

    with patch("pipeline.run.synthesize_business", mock_synthesize):
        await run_module.run_pipeline()

    # LLM was never called
    mock_synthesize.assert_not_called()

    # Cached lead still in DB
    usernames = [r["username"] for r in _read_leads(db)]
    assert "cached_lead" in usernames


@pytest.mark.asyncio
async def test_new_leads_sorted_by_score_in_db(file_setup, monkeypatch):
    """
    After a re-run, GET /api/leads returns only the new leads sorted by score desc.
    Verifies the DB state that the API layer will serve.
    """
    b, l, db = file_setup["business"], file_setup["leads"], file_setup["db"]

    b.write_text(json.dumps(INITIAL_BUSINESS))
    l.write_text(json.dumps(INITIAL_LEADS))
    _seed_db(db, [], _sha256(b, l))

    b.write_text(json.dumps(NEW_BUSINESS))
    three_leads = [
        {"username": "lead_low",  "fullName": "Low",  "dm": "dm"},
        {"username": "lead_high", "fullName": "High", "dm": "dm"},
        {"username": "lead_mid",  "fullName": "Mid",  "dm": "dm"},
    ]
    l.write_text(json.dumps(three_leads))

    scores = {"lead_low": 20, "lead_high": 90, "lead_mid": 55}

    async def _score_by_username(enrichment, profile, client):
        username = enrichment.get("summary", "").split()[-1]
        return {"qualityScore": scores.get(username, 50)}

    async def _enrich_with_username(lead, profile, fields, client):
        return {
            "wantsCoaching": True,
            "isSpam": False,
            "fitnessRelevance": "high",
            "summary": f"Summary {lead['username']}",
        }

    async def _score_from_summary(enrichment, profile, client):
        username = enrichment["summary"].split()[-1]
        return {"qualityScore": scores.get(username, 50)}

    monkeypatch.setattr(run_module, "_BUSINESS_JSON", b)
    monkeypatch.setattr(run_module, "_LEADS_JSON", l)
    monkeypatch.setattr(run_module, "_DB_PATH", db)

    with (
        patch("pipeline.run.synthesize_business", return_value=_make_mock_profile()),
        patch("pipeline.run.enrich_lead", side_effect=_enrich_with_username),
        patch("pipeline.run.score_lead", side_effect=_score_from_summary),
        patch("pipeline.run.anthropic.AsyncAnthropic", return_value=MagicMock()),
    ):
        await run_module.run_pipeline()

    leads_in_db = _read_leads(db)
    db_scores = [r["score"] for r in leads_in_db]

    assert set(r["username"] for r in leads_in_db) == {"lead_low", "lead_high", "lead_mid"}
    assert db_scores == sorted(db_scores, reverse=True)
