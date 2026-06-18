"""GT-5: Pipeline Orchestrator — hash gate, parallel enrichment, SQLite persistence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import anthropic
from tqdm import tqdm

from pipeline.synthesize_business import synthesize_business, BusinessProfile
from pipeline.derive_schema import derive_schema, EnrichmentFieldDef
from pipeline.enrich_lead import enrich_lead
from pipeline.score_lead import score_lead

# Paths relative to project root (caller must set cwd or use absolute paths)
_PROJECT_ROOT = Path(__file__).parent.parent
_BUSINESS_JSON = _PROJECT_ROOT / "data" / "business.json"
_LEADS_JSON = _PROJECT_ROOT / "data" / "leads.json"
_DB_PATH = _PROJECT_ROOT / "hotbox.db"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_meta_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.commit()


def _get_stored_hash(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'input_hash'"
    ).fetchone()
    return row["value"] if row else None


def _set_stored_hash(conn: sqlite3.Connection, hash_val: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('input_hash', ?)",
        (hash_val,),
    )
    conn.commit()


def _reset_leads_table(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS leads")
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
    conn.commit()


def _insert_lead(conn: sqlite3.Connection, lead: dict, enrichment: dict, score: int) -> None:
    enrichment_json = json.dumps(enrichment)
    conn.execute(
        """
        INSERT OR REPLACE INTO leads
            (username, full_name, raw_dm, score, summary, enrichment, status, reply_text)
        VALUES (?, ?, ?, ?, ?, ?, 'inbox', '')
        """,
        (
            lead.get("username", ""),
            lead.get("fullName", ""),
            lead.get("dm", ""),
            score,
            enrichment.get("summary", ""),
            enrichment_json,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------

def _compute_input_hash() -> str:
    try:
        business_bytes = _BUSINESS_JSON.read_bytes()
        leads_bytes = _LEADS_JSON.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"Could not read input files for hashing: {exc}") from exc

    return hashlib.sha256(business_bytes + leads_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Core async pipeline
# ---------------------------------------------------------------------------

async def _process_one_lead(
    lead: dict,
    business_profile: BusinessProfile,
    field_defs: list[EnrichmentFieldDef],
    client: anthropic.AsyncAnthropic,
) -> tuple[dict, dict[str, Any], int]:
    """Run Call A then Call B for a single lead. Returns (lead, enrichment, score)."""
    enrichment = await enrich_lead(lead, business_profile, field_defs, client)
    score_result = await score_lead(enrichment, business_profile, client)
    return lead, enrichment, score_result["qualityScore"]


async def _run_pipeline_async(conn: sqlite3.Connection) -> None:
    """Full pipeline: synthesize → derive schema → parallel enrich+score → store."""
    # GT-1: Business synthesis (sync call wrapped in thread executor to avoid blocking)
    print("Synthesizing business profile...")
    loop = asyncio.get_event_loop()
    business_profile: BusinessProfile = await loop.run_in_executor(
        None, synthesize_business, str(_BUSINESS_JSON)
    )
    print(f"  Business: {business_profile['name']} | {len(business_profile['goals'])} goals")

    # GT-2: Schema derivation (deterministic, instant)
    field_defs = derive_schema(business_profile)
    print(f"  Schema: {len(field_defs)} enrichment fields derived")

    # Load leads
    try:
        leads: list[dict] = json.loads(_LEADS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read leads.json: {exc}") from exc

    # Reset leads table before writing new results
    _reset_leads_table(conn)

    # GT-3 + GT-4: Parallel enrichment and sequential-within-lead scoring
    client = anthropic.AsyncAnthropic()

    tasks = [
        _process_one_lead(lead, business_profile, field_defs, client)
        for lead in leads
    ]

    print(f"Processing {len(leads)} leads...")
    pbar = tqdm(total=len(leads), desc="Processing leads")

    results: list[tuple[dict, dict[str, Any], int]] = []
    for coro in asyncio.as_completed(tasks):
        try:
            result = await coro
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            print(f"\n  Warning: lead processing failed — {exc}")
        finally:
            pbar.update(1)

    pbar.close()

    # Persist results
    for lead, enrichment, score in results:
        _insert_lead(conn, lead, enrichment, score)

    print(f"  Stored {len(results)} leads in SQLite.")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_pipeline() -> None:
    """
    Hash-gated pipeline entry point.
    - If hash matches: no-op (serve from SQLite cache).
    - If hash mismatches: full pipeline re-run + DB reset.
    """
    current_hash = _compute_input_hash()

    conn = _get_connection()
    try:
        _init_meta_table(conn)
        stored_hash = _get_stored_hash(conn)

        if stored_hash == current_hash:
            print("Input files unchanged — serving from cache.")
            return

        print("Input files changed (or first run) — running pipeline...")
        await _run_pipeline_async(conn)
        _set_stored_hash(conn, current_hash)
        print("Pipeline complete. Hash updated.")
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(run_pipeline())
