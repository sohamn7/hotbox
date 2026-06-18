"""SQLite access layer — stdlib sqlite3, no ORM."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.models import LeadResponse

_DB_PATH = Path(__file__).parent.parent / "hotbox.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_lead(row: sqlite3.Row) -> LeadResponse:
    enrichment_raw = row["enrichment"] or "{}"
    try:
        enrichment: dict[str, Any] = json.loads(enrichment_raw)
    except json.JSONDecodeError:
        enrichment = {}

    return LeadResponse(
        username=row["username"],
        full_name=row["full_name"] or "",
        raw_dm=row["raw_dm"] or "",
        score=row["score"] or 0,
        summary=row["summary"] or "",
        enrichment=enrichment,
        status=row["status"] or "inbox",
        reply_text=row["reply_text"] or "",
    )


def get_leads_by_status(status: str) -> list[LeadResponse]:
    """Return all leads with the given status, sorted by score descending."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM leads WHERE status = ? ORDER BY score DESC",
            (status,),
        ).fetchall()
        return [_row_to_lead(r) for r in rows]
    except sqlite3.OperationalError:
        # leads table may not exist yet (before first pipeline run)
        return []
    finally:
        conn.close()


def update_lead_status(username: str, status: str) -> bool:
    """Update lead status. Returns True if a row was modified."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE leads SET status = ? WHERE username = ?",
            (status, username),
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.OperationalError as exc:
        raise RuntimeError(f"DB error updating status for {username}: {exc}") from exc
    finally:
        conn.close()


def update_lead_reply(username: str, reply: str) -> bool:
    """Save reply text and set status='sent'. Returns True if a row was modified."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE leads SET reply_text = ?, status = 'sent' WHERE username = ?",
            (reply, username),
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.OperationalError as exc:
        raise RuntimeError(f"DB error updating reply for {username}: {exc}") from exc
    finally:
        conn.close()
