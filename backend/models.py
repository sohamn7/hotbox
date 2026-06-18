"""Pydantic models for request/response shapes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class LeadResponse(BaseModel):
    username: str
    full_name: str
    raw_dm: str
    score: int
    summary: str
    enrichment: dict[str, Any]
    status: str
    reply_text: str


class StatusUpdate(BaseModel):
    status: Literal["sent", "archive", "inbox"]


class ReplyUpdate(BaseModel):
    reply: str
