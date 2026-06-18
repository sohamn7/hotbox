"""GT-6: FastAPI Backend — 3 endpoints, pipeline startup, CORS."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv

# Load .env from project root before any other imports that need the key
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.db import get_leads_by_status, update_lead_status, update_lead_reply
from backend.models import LeadResponse, StatusUpdate, ReplyUpdate
from pipeline.run import run_pipeline


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run pipeline on startup (hash-gated — no-op if files unchanged)."""
    try:
        await run_pipeline()
    except Exception as exc:  # noqa: BLE001
        # Log but don't crash the server — stale data is better than no server
        print(f"[startup] Pipeline error: {exc}")
    yield


app = FastAPI(title="Hotbox API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "PATCH"],
    allow_headers=["*"],
)


@app.get("/api/leads", response_model=list[LeadResponse])
def list_leads(status: str = "inbox") -> list[LeadResponse]:
    """Return leads filtered by status, sorted by score descending."""
    return get_leads_by_status(status)


@app.patch("/api/leads/{username}/status")
def patch_status(username: str, body: StatusUpdate) -> dict:
    """Update lead status to inbox | sent | archive."""
    updated = update_lead_status(username, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Lead '{username}' not found.")
    return {"ok": True}


@app.patch("/api/leads/{username}/reply")
def patch_reply(username: str, body: ReplyUpdate) -> dict:
    """Save reply text and mark lead as sent."""
    updated = update_lead_reply(username, body.reply)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Lead '{username}' not found.")
    return {"ok": True}
