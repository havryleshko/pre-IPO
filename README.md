# Pre-IPO

**Agent for comparing pre-IPO market predictions with post-IPO filings.**


## What is this

You enter a **company name or ticker**. The system pulls **public** data (SEC filings, news, market feeds), runs one **resumable pipeline**, and returns a **structured JSON result** plus an optional **Claude-written narrative**: outcome-style price metrics, S-1-derived claims and filing facts, and short sections such as pre-IPO story, post-IPO grounding, differences, watch items, and sources. The primary local entrypoint is the **`preipo` CLI**; the **Textual TUI** is an alternate client on top of the same API.

## How it works

Mental model: **one background job per analysis** — `POST /analyses` creates a row and schedules `run_analysis_pipeline`; the client polls `GET /analyses/{id}` or listens on **WebSocket** `/analyses/{id}/progress`.

Inside `**single_agent`** (see `[.cursor/plans/design.md](.cursor/plans/design.md)`):

1. **Resolve** ticker (and IPO date when available) for price history.
2. **Harvest** in parallel: SEC EDGAR, RSS, NewsAPI, Yahoo Finance — plus a post-IPO **10-K** text path when ticker and IPO date exist.
3. **Parse** prospectus-style fields from filings into structured parser output.
4. **Scenario builder** produces scenario output (including price performance fed from IPO-window history).
5. **NarrativeSynthesiser** calls **Anthropic** with a compact prompt; response is parsed into `NarrativeReport` or skipped on failure.
6. **Persist** `final_report` as `SingleAgentResult` (claims, facts, metrics, optional narrative).

Comparison logic today is **implicit**: pre-IPO side is partly **S-1 / news**; post-IPO side is **later filings, metrics, and news** — the narrative step is meant to articulate gaps in plain language when enabled.

## Prerequisites

- **Python** 3.12+ (repo also runs on 3.13 in CI/local)
- **Docker** 24+ (for Compose or `./run-local.sh` Postgres)
- **PostgreSQL** reachable via `DATABASE_URL`
- **SEC EDGAR user agent** in the form `AppName/1.0 (contact@email.com)` — required for SEC requests (`SEC_EDGAR_USER_AGENT`)
- **Optional API keys** (see `[.env.example](.env.example)`): `NEWSAPI_API_KEY`, `CRUNCHBASE_API_KEY`, `FRED_API_KEY`, `TWITTER_BEARER_TOKEN`, `**LLM_API_KEY`** / `LLM_MODEL` (Anthropic — enables narrative sections)

## Quickstart (Docker)

From the repo root:

```bash
docker compose up --build
```

- **API:** `http://localhost:8000`
- **Web UI:** `http://localhost:3000` only if your tree includes the `frontend/` service from `docker-compose.yml` (some checkouts are API + TUI only)

The backend **entrypoint** waits for Postgres, applies **all** SQL files in `backend/database/migrations/` **in filename order**, then starts Uvicorn.

To use the **TUI** against Docker API (from the host):

```bash
cd /path/to/pre-IPO
source .venv/bin/activate
PREIPO_API_URL=http://127.0.0.1:8000 PREIPO_WS_URL=ws://127.0.0.1:8000 python -m tui
```

## Running locally

Install the package (once per venv) so the `preipo` command and imports resolve:

```bash
source .venv/bin/activate
pip install -e ".[test]"
```

**Postgres + migrations** (Docker helper):

```bash
./run-local.sh
```

**API** (port **8000** for local `uvicorn`; Docker Compose also exposes the API on **8000**):

```bash
source .venv/bin/activate
PYTHONPATH=. uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**CLI** (primary local entrypoint; default base URL is `http://127.0.0.1:8000`, override with `PREIPO_API_URL` or `preipo --api-url …`):

```bash
source .venv/bin/activate
preipo doctor
preipo analyze "Arm Holdings"
preipo analyze "Arm Holdings" --show-id --json   # full JSON on stdout; id on stderr
preipo export <analysis_id>
preipo tui                                        # alternate UI on the same API
```

**TUI:**

```bash
source .venv/bin/activate
PREIPO_API_URL=http://127.0.0.1:8000 PREIPO_WS_URL=ws://127.0.0.1:8000 python -m tui
```

Without `./run-local.sh`, create the DB yourself and apply migrations (see **Database migrations**).

## Configuration

Copy `[.env.example](.env.example)` to `.env` and set at least `DATABASE_URL`, `SEC_EDGAR_USER_AGENT`, and any optional keys you need. Point `PREIPO_API_URL` / `PREIPO_WS_URL` at your API if not using the defaults (`127.0.0.1:8000`).

## Database migrations

SQL lives in `[backend/database/migrations/](backend/database/migrations/)`. Apply files **in order** (same as `run-local.sh` and the Docker entrypoint):

- **Local script:** `./run-local.sh` pipes each `*.sql` into `psql` against the Docker Postgres on `127.0.0.1:5432`.
- **Docker:** `backend/entrypoint.sh` runs `psql -f` for each file before Uvicorn.
- **Manual:** `psql` each file with `-v ON_ERROR_STOP=1` against your `DATABASE_URL` database.

## Tests

```bash
pytest tests/ -v
```

## Architecture

Authoritative notes: `[.cursor/plans/design.md](.cursor/plans/design.md)` (pipeline order, `SingleAgentResult`, API contracts, `NarrativeSynthesiser`).

Layout:

- `backend/` — FastAPI app, agents, tools, DB queries, migrations
- `cli/` — `preipo` console entrypoint (HTTP client to the API)
- `tui/` — Textual client
- `tests/` — pytest
- `frontend/` — optional Vite UI (only if present; referenced by `docker-compose.yml`)

