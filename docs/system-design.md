# Hotbox — System Design

## Overview
Hotbox is an Instagram lead enrichment pipeline + triage UI for any business. It ingests a business profile JSON and inbound Instagram leads JSON, runs LLM-powered enrichment and scoring via Anthropic Claude, and surfaces a ranked inbox UI for a business operator to triage leads.

---

## Architecture

```
data/
  business.json        ← operator drops new files here to trigger re-run
  leads.json

Pipeline (Python, FastAPI-callable)
  ├── synthesize_business.py   → 1 LLM call → structured business profile
  ├── derive_schema.py         → deterministic → enrichment field definitions
  ├── enrich_lead.py           → 1 LLM call per lead (Call A) → enrichment + summary
  ├── score_lead.py            → 1 LLM call per lead (Call B) → qualityScore
  └── run.py                   → orchestrator (hash check, tqdm, parallel)

Backend (FastAPI + SQLite)
  ├── GET  /api/leads?status=  → sorted by score desc
  ├── PATCH /api/leads/{u}/status  → inbox/sent/archive
  └── PATCH /api/leads/{u}/reply   → save reply text

Frontend (React + Vite + TypeScript + Tailwind)
  ├── Inbox / Sent / Archive views
  ├── Left panel: lead list (name, one-line teaser, score badge)
  └── Right panel: name | raw DM | rich summary | enrichment fields | reply box
```

---

## Data Flow

1. Page load → FastAPI computes SHA-256 hash of `business.json` + `leads.json`
2. Hash matches stored hash → serve from SQLite (no API calls)
3. Hash differs → reset DB → run full pipeline → store results + new hash
4. React fetches `/api/leads?status=inbox` on load, renders sorted list
5. Operator clicks lead → detail panel renders raw DM + enrichment
6. Send reply → PATCH status=sent → lead disappears from inbox
7. Dismiss → PATCH status=archive → lead disappears from inbox

---

## Pipeline Detail

### Step 1: Business Profile Synthesis (1 LLM call, runs once)
- Input: raw `business.json`
- Output:
```json
{
  "goals": [
    { "label": "coaching signups", "priority": 1 },
    { "label": "product sales", "priority": 2 },
    { "label": "fitness creator collabs", "priority": 3 }
  ],
  "icp": "gym-goers / fitness enthusiasts, 20s-40s, already lifting or want coaching",
  "spamSignals": ["generic compliment with no fitness context", "marketing/growth service offers"],
  "name": "Apex Fuel",
  "location": "online only, ships US"
}
```

### Step 2: Schema Derivation (deterministic, no LLM)
- Input: synthesized business profile (goals array)
- Output: array of enrichment field definitions
```json
[
  { "key": "wantsCoaching", "question": "Does this lead want 1:1 coaching?", "type": "boolean" },
  { "key": "wantsProduct", "question": "Does this lead want to buy supplements?", "type": "boolean" },
  { "key": "wantsCollab", "question": "Is this lead a fitness creator seeking collaboration?", "type": "boolean" },
  { "key": "isSpam", "question": "Is this a spam or irrelevant message?", "type": "boolean" },
  { "key": "fitnessRelevance", "question": "How relevant is this lead to fitness?", "type": "string" }
]
```
- Always appends `isSpam` field based on business spam signals
- One boolean field per business goal

### Step 3: Lead Enrichment — Call A (1 LLM call per lead, parallel)
- Input: lead JSON (bio, DM, posts) + business profile + field definitions
- Output (Anthropic structured output / tool use):
```json
{
  "wantsCoaching": true,
  "wantsProduct": false,
  "wantsCollab": false,
  "isSpam": false,
  "fitnessRelevance": "high — lifts regularly, posts gym content, explicitly stuck on a plateau",
  "summary": "Matt is a 28-year-old recreational lifter from Ohio who's been stuck on his bench and squat for 5+ months. He's tried self-coaching via YouTube and is now actively seeking structured programming and accountability. High intent, genuine fitness context, zero spam signals."
}
```

### Step 4: Lead Scoring — Call B (1 LLM call per lead, after Call A)
- Input: Call A output + business profile (goals, ICP, spamSignals)
- Output: `{ "qualityScore": 87 }`
- Scoring rubric (explicit in prompt):
  - ICP match (age, fitness level, location eligibility): up to 30 pts
  - Goal alignment (matches high-priority goals): up to 40 pts
  - DM quality / intent clarity: up to 20 pts
  - Engagement signals (posts, follower authenticity): up to 10 pts
  - isSpam = true: -60 pt penalty (floor at 0)

---

## SQLite Schema

```sql
CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
-- key='input_hash', value=<sha256>

CREATE TABLE leads (
  username TEXT PRIMARY KEY,
  full_name TEXT,
  raw_dm TEXT,
  score INTEGER,
  summary TEXT,
  enrichment TEXT,   -- JSON object: { fieldKey: value, ... }
  status TEXT DEFAULT 'inbox',  -- inbox | sent | archive
  reply_text TEXT DEFAULT ''
);
```

---

## Goal Targets (immutable harness)

| ID | Component | Contract |
|----|-----------|----------|
| GT-1 | Business Synthesizer | 1 LLM call, structured goals/ICP/spamSignals output |
| GT-2 | Schema Deriver | Deterministic, 1 field per goal + isSpam always present |
| GT-3 | Lead Enricher (Call A) | 1 LLM call per lead, dynamically-constructed structured output schema |
| GT-4 | Lead Scorer (Call B) | 1 LLM call per lead, explicit weighted rubric, runs after GT-3 |
| GT-5 | Pipeline Orchestrator | SHA-256 hash gate, tqdm progress, parallel leads, DB reset on mismatch |
| GT-6 | FastAPI Backend | 3 endpoints: GET leads by status, PATCH status, PATCH reply |
| GT-7 | React Inbox UI | Inbox/Sent/Archive, sorted by score, detail panel with enrichment rows |

---

## Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Pipeline | Python 3.12 | Anthropic SDK most mature, asyncio for parallel leads |
| LLM | Claude Haiku 4.5 | Fast, cheap, sufficient for structured extraction |
| Structured outputs | Anthropic tool use | Guarantees valid JSON, dynamic schema support |
| Backend | FastAPI | Lightweight, async, easy SQLite integration |
| Database | SQLite | Zero setup, single file, fits local-only use case |
| Frontend | React + Vite + TypeScript | Fast dev, component model fits inbox layout |
| Styling | Tailwind CSS | Utility-first, no design system overhead |

---

## Non-Goals
- No actual Instagram API integration (mock data only)
- No authentication / multi-user
- No file upload UI (operator replaces files directly in `data/`)
- No deployment (local only)
