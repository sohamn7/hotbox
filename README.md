# Hotbox

Instagram lead enrichment pipeline + triage inbox UI.

## Quick Start

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API key
```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Start the backend
```bash
# Run from the project root (hotbox/)
uvicorn backend.main:app --reload
```

The first startup will run the full pipeline against `data/business.json` and `data/leads.json`.
Subsequent startups are instant if the files haven't changed (hash-cached).

### 4. Start the frontend
```bash
cd frontend
npm install
npm run dev
```

### 5. Open the app
Visit `http://localhost:5173`

---

## Updating leads

Replace `data/business.json` or `data/leads.json`, then restart the backend (or the page load will trigger a re-run automatically via hash check).

## Project structure
```
data/           Input JSON files
pipeline/       Python enrichment pipeline
backend/        FastAPI server + SQLite layer
frontend/       Vite + React + TypeScript UI
hotbox.db       SQLite database (auto-created)
```
