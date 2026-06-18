"""
GT-6 FastAPI endpoint tests.
Uses an in-memory temp SQLite seeded with fixture data.
Pipeline startup is patched out — no LLM calls.
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch):
    """Create a temp SQLite DB seeded with test leads and patch the db module."""
    db_file = tmp_path / "test_hotbox.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        """
        CREATE TABLE leads (
            username    TEXT PRIMARY KEY,
            full_name   TEXT,
            raw_dm      TEXT,
            score       INTEGER,
            summary     TEXT,
            enrichment  TEXT,
            status      TEXT DEFAULT 'inbox',
            reply_text  TEXT DEFAULT ''
        )
        """
    )
    seed = [
        ("lead_a", "Alice A.", "DM from Alice", 85, "High-intent lead.", '{"isSpam": false}', "inbox", ""),
        ("lead_b", "Bob B.",   "DM from Bob",   40, "Medium-intent lead.", '{"isSpam": false}', "inbox", ""),
        ("spam_c", "Spammer",  "Buy followers", 5,  "Spam lead.",         '{"isSpam": true}',  "inbox", ""),
        ("sent_d", "Dana D.",  "DM from Dana",  70, "Sent lead.",         '{"isSpam": false}', "sent",  "Great reply"),
    ]
    conn.executemany(
        "INSERT INTO leads VALUES (?,?,?,?,?,?,?,?)", seed
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("backend.db._DB_PATH", db_file)
    return db_file


@pytest.fixture()
def client(tmp_db):
    """FastAPI TestClient with pipeline startup patched to a no-op."""
    with patch("pipeline.run.run_pipeline", new_callable=lambda: lambda: AsyncMock(return_value=None)):
        from backend.main import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


# ---------------------------------------------------------------------------
# GET /api/leads
# ---------------------------------------------------------------------------

def test_get_inbox_returns_inbox_leads(client):
    resp = client.get("/api/leads?status=inbox")
    assert resp.status_code == 200
    data = resp.json()
    assert all(lead["status"] == "inbox" for lead in data)


def test_get_inbox_sorted_by_score_desc(client):
    resp = client.get("/api/leads?status=inbox")
    scores = [lead["score"] for lead in resp.json()]
    assert scores == sorted(scores, reverse=True)


def test_get_sent_returns_sent_leads(client):
    resp = client.get("/api/leads?status=sent")
    assert resp.status_code == 200
    data = resp.json()
    assert all(lead["status"] == "sent" for lead in data)


def test_get_leads_response_shape(client):
    resp = client.get("/api/leads?status=inbox")
    for lead in resp.json():
        assert "username" in lead
        assert "full_name" in lead
        assert "raw_dm" in lead
        assert "score" in lead
        assert "summary" in lead
        assert "enrichment" in lead
        assert "status" in lead
        assert "reply_text" in lead
        assert isinstance(lead["enrichment"], dict)
        assert isinstance(lead["score"], int)


def test_get_archive_empty_initially(client):
    resp = client.get("/api/leads?status=archive")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# PATCH /api/leads/{username}/status
# ---------------------------------------------------------------------------

def test_patch_status_to_archive(client):
    resp = client.patch("/api/leads/lead_a/status", json={"status": "archive"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_patch_status_lead_no_longer_in_inbox(client):
    client.patch("/api/leads/lead_a/status", json={"status": "archive"})
    inbox = [l["username"] for l in client.get("/api/leads?status=inbox").json()]
    assert "lead_a" not in inbox


def test_patch_status_archived_lead_appears_in_archive(client):
    client.patch("/api/leads/lead_a/status", json={"status": "archive"})
    archive = [l["username"] for l in client.get("/api/leads?status=archive").json()]
    assert "lead_a" in archive


def test_patch_status_404_on_missing_lead(client):
    resp = client.patch("/api/leads/no_such_user/status", json={"status": "archive"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/leads/{username}/reply
# ---------------------------------------------------------------------------

def test_patch_reply_saves_text(client):
    resp = client.patch("/api/leads/lead_b/reply", json={"reply": "Thanks for reaching out!"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_patch_reply_moves_lead_to_sent(client):
    client.patch("/api/leads/lead_b/reply", json={"reply": "Hey!"})
    sent = [l["username"] for l in client.get("/api/leads?status=sent").json()]
    assert "lead_b" in sent


def test_patch_reply_lead_no_longer_in_inbox(client):
    client.patch("/api/leads/lead_b/reply", json={"reply": "Hey!"})
    inbox = [l["username"] for l in client.get("/api/leads?status=inbox").json()]
    assert "lead_b" not in inbox


def test_patch_reply_404_on_missing_lead(client):
    resp = client.patch("/api/leads/ghost/reply", json={"reply": "hello"})
    assert resp.status_code == 404
