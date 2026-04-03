# pre-IPO — design (current implementation)

This document describes the **code as it exists today**. Older multi-agent / judge / checkpoint narratives are out of scope unless they appear in the repo.

## Purpose

User provides a **company name**. The system pulls **public** data (SEC filings, optional news/market/macro feeds), parses the prospectus-style content, builds **scenario-style outputs** and a **structured final result** suitable for a non-expert reader. Outputs are **research aids**, not advice.

## Runtime shape

- **API:** FastAPI on port **8001** in local docs (`uvicorn`), or **8000** under `docker compose`.
- **Client:** **Textual TUI** (`python -m tui`) talks to the API and WebSocket progress.
- **Database:** PostgreSQL; connection string in `DATABASE_URL` (`postgresql+asyncpg://...` in app config; asyncpg normalises to `postgresql://`).

Local bootstrap: `./run-local.sh` starts Postgres in Docker, applies SQL under `backend/database/migrations/`, then you run API + TUI in separate shells (see `README.md`).

## Pipeline (single resumable stage)

Orchestration is **not** a multi-node LangGraph chain of separate agents in production. There is one logical pipeline step:

| Layer | Role |
|--------|------|
| `resume_service` | `_PIPELINE_ORDER = ("single_agent",)`. Sets `running` → runs retry wrapper → sets `completed` or `failed`. |
| `retry_service` | Runs the executor once; if output is missing or (for `single_agent`) **invalid** vs `SingleAgentResult`, runs again; if still bad, `set_analysis_failed` with that agent name and raises. |
| `SingleAgentToolCaller` | Harvester → prospectus parser → scenario builder → **`NarrativeSynthesiser`** (optional Claude call) → assembles **`final_report`** (`SingleAgentResult` with optional `NarrativeReport`) and persists it. |
| `pipeline_runner` | Wraps the executor for WebSocket status (`running` / `failed` / `completed`). |

**Resume:** `last_completed_agent == "single_agent"` means the row is treated as finished for this pipeline; a new run does not re-execute the stage.

**Failure metadata:** If `retry_service` already set `status=failed` and `last_completed_agent`, the resume layer **does not** call `set_analysis_failed` again (avoids overwriting the failing agent with a stale checkpoint).

## Data model (API vs DB)

- **POST `/analyses`** — creates a row, schedules `run_analysis_pipeline` in the background.
- **GET `/analyses/{id}`** — returns `AnalysisOutputsResponse`: metadata plus **`analysis_result`**, parsed from JSON column `final_report`. If `final_report` is missing, wrong type, or fails `SingleAgentResult` validation, **`analysis_result` is `null`** and a warning is logged (response stays **200**).

## Key persistence

Table **`analyses`** (see migrations): among others, `harvester_output`, `parser_output`, `scenario_output`, `final_report`, `status`, `last_completed_agent`, `complexity_tier`, ticker/IPO fields where used.

## Configuration

`backend/config/settings.py` (env / `.env`): database, CORS, optional API keys (SEC user agent, News, Crunchbase, FRED, Twitter), timeouts, **`llm_api_key` / `llm_model` / `llm_base_url`**. Set `LLM_API_KEY` to an Anthropic key to enable narrative synthesis; if unset the pipeline completes without a narrative and `analysis_result.narrative` is `null`.

### NarrativeSynthesiser

`backend/agents/narrative_synthesiser.py` — called inside `SingleAgentToolCaller.run()` after `ScenarioBuilder`, before `save_final_report`. Builds a structured prompt from S-1 claims, filing facts, outcome metrics, and up to five news articles, then calls `anthropic.Anthropic.messages.create` with `llm_model` (default `claude-sonnet-4-6`). Parses the JSON response into a `NarrativeReport` (fields: `headline`, `pre_ipo_story`, `post_ipo_grounding`, `key_differences`, `watch_items`, `sources_cited`). Any exception is logged as a warning and returns `None` — the pipeline never fails due to the LLM step.

## External behaviour

- SEC and other tools live under `backend/tools/`. Failures are generally **partial** where the harvester uses `gather(..., return_exceptions=True)` pattern; the pipeline can still complete with thinner data.
- **Startup:** If Postgres refuses TCP, startup logs an explicit line pointing at `./run-local.sh` before re-raising.

## Testing

- **`pytest tests/`** — primary gate. Integration tests patch DB and network; `tests/integration/test_analysis_end_to_end.py` exercises the single-agent JSON outputs with fixtures.
- **Live E2E** (human): `./run-local.sh` → uvicorn → TUI or `curl` POST + poll GET until `status` is terminal and `analysis_result` is present.

## Future (explicitly not implemented here)

- **Finer-grained LLM evaluation** (claim-by-claim grading, structured extraction) — extend `NarrativeSynthesiser` or add a separate evaluator agent after this pipeline is stable.
- **Finer-grained resume** inside `SingleAgentToolCaller` (harvester vs parser vs scenario) — would require new `last_completed_agent` semantics and migrations.
