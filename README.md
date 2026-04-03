# pre-IPO

This project is a **pre-IPO research assistant**. You give it a company name; it runs an automated pipeline that pulls public filings and related data, then produces structured analysis meant to be readable for people who are not finance experts—plain language, clear verdict-style framing, and actionable angles.

It is aimed at the kind of pain advisors and curious investors feel: IPO research is scattered across filings, news, and market data, and hard to assemble quickly. The app does **not** replace a human advisor or legal due diligence; treat outputs as research aids, not buy or sell instructions.

## What you get

- A **Textual TUI** to start an analysis, watch progress, and view results in the terminal.
- A **Python API** (FastAPI) that stores each run in **PostgreSQL** and runs the analysis pipeline.
- **Resume-friendly runs**: if something fails mid-pipeline, the design favors picking up from where things stopped rather than throwing everything away.

## What it is built with

- **Backend:** Python 3.12+, FastAPI, async PostgreSQL (`asyncpg`).
- **TUI:** Textual (Python).
- **Data:** SEC EDGAR and other configurable sources (see `.env.example` for API keys you may enable).

## Running everything with Docker

From the repo root:

```bash
docker compose up --build
```

- API: `http://localhost:8000`

The backend waits for Postgres and applies the first database migration on startup. If you add or change SQL under `backend/database/migrations/`, apply new files in order (for example with `psql`) so your database schema stays in sync.

## Running locally without Compose

You need Python and Postgres reachable at the URL in your env.

1. Copy `.env.example` to `.env` and adjust values (especially `DATABASE_URL` and `SEC_EDGAR_USER_AGENT`; SEC expects a descriptive user agent with contact info).
2. Create the database and run migrations in order from `backend/database/migrations/`.
3. Start the API: `source .venv/bin/activate && PYTHONPATH=. uvicorn backend.main:app --host 127.0.0.1 --port 8001`
4. Start the TUI: `source .venv/bin/activate && PREIPO_API_URL=http://127.0.0.1:8001 PREIPO_WS_URL=ws://127.0.0.1:8001 python -m tui`

There is a helper script `./run-local.sh` that starts Postgres in Docker and applies migrations; then run API and TUI in separate terminals as the script prints.

## Configuration

See **`.env.example`** for all supported variables: database URL, CORS origins, optional news and data API keys, timeouts, and logging.

## Tests

```bash
pytest tests/ -v
```

## Project layout (short)

- `backend/` — API, agents, database access, pipeline services  
- `tui/` — Textual terminal UI client  
- `tests/` — pytest suite  
- `.cursor/plans/design.md` — deeper architecture notes for contributors  

---

*This software is for research and education. It is not financial, legal, or investment advice.*
