# Task List — IPO Intelligence

## Inputs Reviewed

- Architecture source: /Users/ohavryleshko/Documents/GitHub/pre-IPO/.cursor/plans/design.md
- Current repo state is scaffold-only (README, CI workflow, no backend/frontend code yet).

## Proposed tasks.md Content (Atomic, Ordered)

- T001 Create `backend/config/settings.py` Pydantic settings model for env vars and API keys.
- T002 Create `backend/database/connection.py` async PostgreSQL connection factory.
- T003 Create `backend/database/queries.py` parameterized query functions for analyses lifecycle.
- T004 Create `backend/database/migrations/001_create_core_tables.sql` for `analyses`, `agent_runs`, `checkpoints`, `agent_improvements`.
- T005 Create `backend/models/analysis.py` Pydantic models for top-level analysis records.
- T006 Create `backend/models/harvester_output.py` Pydantic schema for Data Harvester output.
- T007 Create `backend/models/parser_output.py` Pydantic schema for Prospectus Parser output.
- T008 Create `backend/models/scenario_output.py` Pydantic schema for Scenario Builder output.
- T009 Create `backend/models/recommendation_output.py` Pydantic schema for Recommendation Engine output.
- T010 Create `backend/models/judge_output.py` Pydantic schema for Judge Agent output.
- T011 Create `backend/services/checkpoint_service.py` save/load checkpoint functions by `analysis_id`.
- T012 Create `backend/services/analysis_status_service.py` update `status` and `last_completed_agent` transitions.
- T013 Create `backend/services/agent_run_logger.py` start/end/error logging to `agent_runs`.
- T014 Create `backend/agents/complexity_classifier.py` complexity tier classifier (simple/standard/complex).
- T015 Create `backend/agents/lead_orchestrator.py` planning + parallel subagent dispatch skeleton. (using langgraph)
- T016 Create `backend/agents/data_harvester.py` parallel source fetch orchestration with `asyncio.gather` and failure capture.
- T017 Create `backend/tools/sec_edgar_client.py` SEC search + filing fetch helper.
- T018 Create `backend/tools/rss_client.py` RSS fetch + 30-day filter helper.
- T019 Create `backend/tools/newsapi_client.py` NewsAPI search helper with quota-safe usage.
- T020 Create `backend/tools/crunchbase_client.py` Crunchbase lookup helper and single-request policy.
- T021 Create `backend/tools/yfinance_client.py` comparable-company fetch helper.
- T022 Create `backend/tools/fred_client.py` FRED macro fetch helper with TTL cache hook.
- T023 Create `backend/tools/twitter_client.py` verified-account-only query helper.
- T024 Create `backend/agents/prospectus_parser.py` parser pipeline reading `harvester_output` and writing `parser_output`.
- T025 Create `backend/agents/scenario_builder.py` rules engine + bounded LLM adjustment + sum-to-100 enforcement.
- T026 Create `backend/agents/recommendation_engine.py` dual-goal recommendation generator (pre-IPO beneficiary funds + post-IPO positioning).
- T027 Create `backend/agents/judge_agent.py` validation checklist + retry-once logic + flags.
- T028 Create `backend/services/retry_service.py` null-output contract implementation for per-agent retry.
- T029 Create `backend/services/resume_service.py` resume-from-`last_completed_agent` workflow. (using langgraph)
- T030 Create `backend/api/schemas.py` FastAPI request/response models (`company_name` input and analysis outputs).
- T031 Create `backend/api/routes_analysis.py` endpoints for create analysis, fetch analysis, confirm flags. (using langgraph)
- T032 Create `backend/api/routes_export.py` endpoints for summary/full PDF export and lock checks.
- T033 Create `backend/api/websocket_progress.py` WebSocket broadcaster for per-agent status/tool-call updates. (using langgraph)
- T034 Create `backend/main.py` FastAPI app wiring routes, startup hooks, and websocket registration. (using langgraph)
- T035 Create `backend/export/pdf_summary.py` one-page export generator.
- T036 Create `backend/export/pdf_full_report.py` multi-page export generator.
- T037 Create `frontend/src/api/client.ts` API/WebSocket client methods for analyses and progress updates.
- T038 Create `frontend/src/components/AnalysisInputPanel.tsx` company input, generate button, complexity badge.
- T039 Create `frontend/src/components/AgentProgressPanel.tsx` agent status list + tool-call activity feed.
- T040 Create `frontend/src/components/ScenarioCards.tsx` three-card scenario view with sourced drivers/risks/targets.
- T041 Create `frontend/src/components/FlagsPanel.tsx` amber flags display + confirm flags action.
- T042 Create `frontend/src/components/ReportPanels.tsx` summary, sentiment bar, source timestamps, export controls.
- T043 Create `frontend/src/App.tsx` two-column layout and state orchestration.
- T044 Create `tests/agents/test_complexity_classifier.py` classifier tier coverage tests.
- T045 Create `tests/agents/test_data_harvester_parallel.py` parallel execution + partial-failure continuation tests.
- T046 Create `tests/agents/test_prospectus_parser.py` S-1 extraction and missing-section flagging tests.
- T047 Create `tests/agents/test_scenario_builder_rules.py` rule triggers, LLM adjustment cap, and normalization tests.
- T048 Create `tests/agents/test_recommendation_engine.py` positioning presence, risk warning, paragraph length constraints.
- T049 Create `tests/agents/test_judge_agent.py` validation, retry outcomes, flag/export lock behavior.
- T050 Create `tests/integration/test_pipeline_resume.py` checkpoint resume from failed agent. (using langgraph)
- T051 Create `tests/integration/test_null_output_contract.py` null-write retry-once then fail-fast behavior.
- T052 Create `tests/integration/test_analysis_end_to_end.py` full pipeline happy-path with 3 scenarios. (using langgraph)
- T053 Create `tests/api/test_analysis_routes.py` analysis API contract tests.
- T054 Create `tests/api/test_websocket_progress.py` real-time status broadcast tests. (using langgraph)
- T055 Create `tests/export/test_pdf_generation.py` summary/full export content smoke tests.
- T056 Create `docker-compose.yml` services for frontend, backend, PostgreSQL with persistent volume.
- T057 Create `requirements.txt` backend dependency manifest aligned to architecture stack. (using langgraph)
- T058 Create `.env.example` required environment variables and safe defaults.
- T059 Update `.github/workflows/ci.yaml` to include migration/setup steps required by new test suite. (using langgraph)
- T060 Update `README.md` with local setup, runbook, and testing commands.

## Execution Notes

- Keep one-task-per-conversation discipline for Worker mode.
- Run `pytest tests/ -v` after each meaningful batch in Judge mode.
- Do not mark tasks done until both local and CI pass.