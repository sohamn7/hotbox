# Hotbox — Research & Decision Log

## LLM Model Selection

### Why Claude Haiku 4.5
- Fixed budget constraint → minimize cost per call
- Each lead requires 2 calls; N leads = 2N + 1 (business synthesis) total calls
- Haiku 4.5 (`claude-haiku-4-5-20251001`) is the fastest and cheapest Anthropic model
- Structured extraction (boolean fields, short strings) does not require Sonnet-level reasoning
- Scoring with explicit weighted rubric is deterministic enough for Haiku

### Two-Call Chain vs Single Call
- Option: single call does enrichment + score simultaneously
- Rejected: scoring grounded in enrichment is more accurate (chain-of-thought effect)
- Chosen: Call A (enrich) → Call B (score from enrichment) per lead
- Cost: 2x calls but significantly better score accuracy for ICP matching

---

## Structured Outputs Strategy

### Anthropic Tool Use for JSON Enforcement
- Anthropic's tool use API allows defining a JSON schema; model is forced to return valid JSON matching it
- Dynamic schema: schema is constructed at runtime from business goals (not hardcoded)
- Process:
  1. GT-2 (Schema Deriver) outputs `EnrichmentFieldDef[]`
  2. These are converted to a JSON Schema object for the Anthropic `tools` parameter
  3. Call A uses this schema — model cannot deviate from field names or types

### Schema Construction Example
```python
def build_tool_schema(field_defs: list[dict]) -> dict:
    properties = {}
    for f in field_defs:
        if f["type"] == "boolean":
            properties[f["key"]] = {"type": "boolean", "description": f["question"]}
        else:
            properties[f["key"]] = {"type": "string", "description": f["question"]}
    properties["summary"] = {
        "type": "string",
        "description": "Rich summary: who is this lead, what do they want, notable details from posts/DM"
    }
    return {
        "name": "enrich_lead",
        "description": "Enrich a lead with structured fields and a summary",
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties.keys())
        }
    }
```

---

## Change Detection

### SHA-256 File Hashing
- On every backend startup (page load triggers a check endpoint), compute:
  `hash = sha256(business.json_bytes + leads.json_bytes)`
- Compare to `meta` table row `key='input_hash'`
- Mismatch → full pipeline re-run + DB reset
- Match → no-op, serve from SQLite
- Why SHA-256: collision-resistant, fast on small files, stdlib (`hashlib`)

---

## Parallelism Strategy

### asyncio + Anthropic async client
- Business synthesis runs first (synchronous gate)
- Schema derivation runs after (deterministic, instant)
- Leads processed with `asyncio.gather()` — all leads run Call A in parallel
- Call B per lead runs immediately after its own Call A (sequential within a lead)
- tqdm wraps an `as_completed` pattern for progress display

### Rate Limiting
- Anthropic Haiku has generous rate limits; N=~10-50 leads won't hit them
- No explicit rate limiting needed for expected data sizes

---

## SQLite Design Decisions

### Why not PostgreSQL / a real DB
- Local-only tool, single user, no concurrent writes
- SQLite is zero-setup, ships with Python stdlib
- Single file → trivial to reset (DROP TABLE + recreate)

### Enrichment field storage
- Stored as `TEXT` column containing JSON string (`enrichment`)
- Keys are dynamic (change per business profile) → can't use fixed columns
- Frontend receives parsed JSON, renders each key-value pair as a labeled row
- On schema change (new business profile) → full DB reset anyway, so no migration needed

---

## Frontend Design Decisions

### Outlook-style Inbox
- Three-panel layout: left nav (view switcher) + center list + right detail
- Lead list item: avatar placeholder + full name + score badge + one-line summary teaser
- Detail panel: sticky header (name + score), raw DM in a styled quote block, summary paragraph, enrichment fields as `<dt>/<dd>` pairs, reply textarea at bottom
- Score badge color: green (70+), yellow (40-69), red (<40)

### State Management
- Local React state + fetch on mount — no Redux/Zustand needed at this scale
- Optimistic UI: on Send/Dismiss, immediately remove from list, PATCH in background
- On error: revert (re-fetch)

### No file upload UI
- Operator replaces `data/business.json` and `data/leads.json` directly
- Refreshing the browser page triggers hash check → pipeline re-run if needed
- Simpler, fits the local dev tool use case

---

## Scoring Rubric (for Call B prompt)

```
Score this lead 0-100 for the business based on the enrichment data.

Rubric (additive, floor at 0):
- ICP match (demographics, fitness relevance, US-based): 0-30 pts
- Goal alignment (matches business's priority goals, highest priority = most pts): 0-40 pts  
- DM quality (specific ask, genuine intent, not copy-paste): 0-20 pts
- Engagement authenticity (real posts, genuine follower ratio): 0-10 pts
- PENALTY: isSpam=true → subtract 60 pts (minimum score: 0)

Prioritize goal alignment above all else. A lead that perfectly matches the #1 goal
should score 80+ even with weak engagement signals.
```
