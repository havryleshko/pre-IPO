# IPO Intelligence — Architecture Document
**Save to:** `.cursor/plans/architecture.md`
**Version:** 2.1 — Data sources, schema, ambiguous tests, build phase agents

---

## North Star

**The exact pain:** financial advisors etc. need to research each company pre-IPO a lot and it’s hard to gather all the info manually real-time + retail investors do not know where to invest for IPO gains

**Who feels it:** Independent Financial Advisors (IFAs) and RIAs, investors

**What success looks like:** pre-IPO research system that does most accurate and precise analysis (Positive, Pessimistic, Realistic) and recommendation what ETF/fund to buy

---

## Anthropic Multi-Agent Principles Applied

This architecture implements all 8 principles from Anthropic's production multi-agent research system.

| Principle | Applied Where |
|---|---|
| 1. Think like your agents | Prompt design section + simulation requirement |
| 2. Teach the orchestrator how to delegate | Lead Agent task description spec |
| 3. Scale effort to query complexity | Complexity classifier |
| 4. Tool design and selection are critical | Tool descriptions per agent |
| 5. Let agents improve themselves | Judge Agent self-improvement loop |
| 6. Start wide, then narrow down | Data Harvester search strategy |
| 7. Guide the thinking process | Extended thinking + interleaved thinking |
| 8. Parallel tool calling | Data Harvester asyncio.gather + subagent parallelism |

---

## Architecture Pattern: Orchestrator-Worker

**Pattern:** One Lead Agent coordinates. Four specialist subagents execute in parallel. One Judge Agent validates.

This is NOT a flat sequential chain. The Lead Agent spawns subagents, each with their own context window, operating independently before reporting back.

```
User Input (company name)
        ↓
  [Lead Orchestrator]
  saves plan to memory
  classifies complexity
        ↓ spawns in parallel
  ┌─────┬──────┬──────┬──────┐
  ↓     ↓      ↓      ↓      ↓
[DH]  [PP]   [SB]   [RE]
Data  Parse  Scen   Reco
Harv  Prosp  Build  Engin
        ↓     ↓      ↓      ↓
  each agent writes directly to PostgreSQL
  passes analysis_id reference only
               ↓
         [Judge Agent]
         validates + flags
         self-improvement log
               ↓
        Final Report → Frontend
```

**Key architectural decisions from Anthropic's production system:**
- Each subagent has its own context window — prevents token overflow on large S-1 filings
- Parallel execution cuts analysis time by up to 90%
- Each agent writes output directly to PostgreSQL, passes only `analysis_id` back — not full JSON
- This prevents information loss and reduces token overhead across the pipeline
- Pipeline resumes from last checkpoint on failure — never restarts from zero

---

## Data Sources

### Pipeline Input Schema

```json
{
  "company_name": "string (required)",
}
```

### Null Output Contract

If any agent writes nothing to the database (silent crash, timeout, or empty JSON):
1. Lead Orchestrator detects null on `analysis_id` read
2. Auto-retry that specific agent once with identical inputs
3. If still null after retry → pipeline halts, clear error to frontend, `status = 'failed'` in `analyses` table
4. IFA sees: "Analysis failed at [Agent Name]. Please try again or contact support."
5. Partial outputs from completed agents are preserved in the DB for debugging

This is intentional. A null output from a core agent means downstream agents will hallucinate to fill the gap. A loud halt is safer than a silent partial report.

Agent returns {} or fields are null → legitimate empty, continue with what's available, flag the gaps
Agent writes nothing at all to the DB → crash, apply the null output contract

### Source Specifications

| Source | What It Returns | Format | Auth | Rate Limit | Fetch Strategy |
|---|---|---|---|---|---|
| SEC EDGAR | S-1 filing text, filing index | Step 1: JSON (efts.sec.gov) → Step 2: raw HTML/XML | None | None (be courteous, max 10 req/sec) | Search API returns filing URL → fetch document → parse with BeautifulSoup |
| RSS Feeds | Recent news articles | XML (feedparser parses to dict) | None | None | Pull on each analysis, filter last 30 days |
| NewsAPI | Article headlines + snippets | JSON — **snippets only on free tier, not full body** | API key | 100 req/day (free developer tier) | Use for discovery — fetch full article via URL if needed |
| Crunchbase | Funding rounds, investors, valuations | JSON | API key | **200 req/month (free tier)** — use sparingly | One lookup per company per analysis, cache result |
| Yahoo Finance (yfinance) | Comparable company P/E, sector multiples | Python objects (no direct API call) | None | Soft limit — avoid hammering | Fetch comps list once, batch ticker lookups |
| FRED API | Fed funds rate, macro indicators | JSON | API key | 120 req/min | Fetch once per analysis, cache for 24 hours |
| X/Twitter API v2 | Posts from verified accounts | JSON | Bearer token | **500k tweets/month, 1 app (free tier)** | Search by company name + ticker, filter verified accounts, last 90 days |

### Rate Limit Risk Register

| Source | Monthly Budget | Est. Usage at 100 analyses/month | Risk |
|---|---|---|---|
| Crunchbase | 200 req/month | 100 req (1/analysis) | **HIGH** — hits limit at 200 analyses |
| NewsAPI | ~3,000 req/month (100/day) | 300 req (3/analysis) | Low |
| X/Twitter | 500k tweets/month | ~50k (500/analysis) | Low |
| SEC EDGAR | Unlimited | — | None |
| FRED | ~3.6M req/month | ~100 (1/analysis, cached) | None |

| Crunchbase | 200 req/month | 100 req (1/analysis) | Low at MVP — monitor at 150+ analyses/month |

Implement basic caching in PostgreSQL. Don't over-engineer, revisit if you hit 150 analyses/month.

---

## ⚖️ Principle 3: Scale Effort to Query Complexity

Before spawning any agents, the Lead Orchestrator classifies query complexity.

### Complexity Classifier

**Simple IPO** (small company, limited public data, pre-S-1):
- 3 data sources (SEC EDGAR, NewsAPI, Crunchbase)
- 3-5 tool calls per source
- Target: 60 seconds

**Standard IPO** (mid-size, S-1 filed, moderate coverage):
- 5 data sources (add Yahoo Finance + FRED)
- 5-10 tool calls per source
- Target: 90 seconds

**Complex IPO** (SpaceX-tier: massive filing, all sources, high public interest):
- All 7 data sources
- 10-15 tool calls per source
- Extended thinking enabled on Lead Agent
- Interleaved thinking on all subagents
- Target: 3-5 minutes

**Prompt rule embedded in Lead Agent:**
> "Before spawning subagents, assess query complexity. Simple: 3 sources, 3-5 tool calls each. Standard: 5 sources, 5-10 tool calls each. Complex: all 7 sources, 10-15 tool calls each. Never over-invest in simple queries."

---

## 🤖 Agent Map

6 roles. One job each. Roles never mixed in a single prompt.

---

### Lead Orchestrator

**Single responsibility:** Analyse query, assess complexity, save plan to memory, spawn subagents with precise task descriptions, synthesise results.

**Principle 1 — Think like your agent:**
Before writing any prompt for this agent, simulate it in Anthropic Console with exact tools and prompts. Watch step-by-step. Common failure modes: spawning too many subagents for simple queries, vague task descriptions causing duplicate work, not saving plan to memory before context overflows.

**Principle 2 — Teach the orchestrator how to delegate:**
Each subagent task description must include:
- Objective (exactly what to find)
- Output format (exact JSON schema)
- Tools to use (explicit list)
- Sources to prioritise
- Task boundaries (what NOT to do — prevents duplication)
- Expected tool call count

**Bad delegation (causes duplicate work):**
> "Research SpaceX's financials."

**Good delegation (prevents duplicate work):**
> "Extract SpaceX's financial metrics from SEC EDGAR S-1 filing only. Find: revenue (annual), burn rate (monthly), cash runway (months), use of proceeds. Output as financials JSON schema. Do NOT search news — that is covered by another subagent. Use 5-8 tool calls maximum. If a metric is missing, mark null and flag."

**Principle 7 — Extended thinking:**
Lead Orchestrator uses extended thinking to assess complexity, plan subagent division of labour, avoid overlap, and decide whether more research is needed after first round.

**Memory checkpoint:**
Lead Orchestrator saves its plan to the `checkpoints` table immediately after complexity assessment. If context window approaches 200,000 tokens, plan is retrievable without restarting.

```python
plan = {
    "analysis_id": "uuid",
    "company_name": "string",
    "complexity": "simple | standard | complex",
    "active_sources": ["array"],
    "subagent_tasks": ["array of precise task descriptions"],
    "checkpoint": "planning_complete",
    "planned_at": "ISO8601"
}
# Write to PostgreSQL checkpoints table immediately before spawning subagents
```

---

### Agent 1: Data Harvester (Subagent)

**Single responsibility:** Find and ingest all public data about the IPO company from assigned sources.

**Principle 4 — Tool design:**
Each tool has a distinct purpose, clear description, and explicit heuristics. No overlap between tools.

**Principle 6 — Start wide, then narrow:**
Prompt embeds search strategy:
> "Start with short, broad queries (1-3 words). Evaluate results. Then progressively narrow. Never start with long specific queries. Start with 'SpaceX funding' then narrow based on what you find."

**Principle 8 — Parallel tool calling:**
All active sources fetched simultaneously via `asyncio.gather()`:

```python
results = await asyncio.gather(
    fetch_sec_edgar(company_name),
    fetch_rss_feeds(company_name),
    fetch_news_api(company_name),
    fetch_crunchbase(company_name),
    fetch_yahoo_finance(company_name),
    fetch_fred_data(),
    fetch_twitter(company_name),
    return_exceptions=True  # one failure never kills the rest
)
```

**Tool descriptions (Principle 4):**
- `sec_edgar_search` — "Search SEC EDGAR for company filings. Use for S-1, prospectus documents. Primary source — always check here first."
- `rss_feed_reader` — "Read RSS feeds for real-time news. Use for breaking IPO news, executive statements. Returns articles from last 30 days."
- `news_api_search` — "Search NewsAPI for historical coverage. Start with broad company name, then narrow by topic."
- `crunchbase_lookup` — "Look up startup funding data. Use for funding rounds, investor names, valuations, cap table."
- `yahoo_finance_data` — "Fetch comparable public company multiples and sector performance. Do NOT use for the IPO company itself — use SEC EDGAR for that."
- `fred_macro_data` — "Fetch Federal Reserve macroeconomic data. Always fetch this — macro context affects every IPO."
- `twitter_search` — "Search X/Twitter for verified accounts only. Use for CEO statements, named institutional investor commentary. Do NOT use for anonymous retail sentiment — too noisy."

**Inputs:**
- `company_name: string` (required)
- `active_sources: array` (from complexity classifier)
- `task_boundaries: string` (from Lead Orchestrator)

**Output written directly to PostgreSQL** (`analyses.harvester_output`). Returns `analysis_id` only to Lead Orchestrator.

```json
{
  "company_name": "string",
  "complexity_tier": "simple | standard | complex",
  "sec_filings": [{"url": "string", "text": "string", "filing_type": "string"}],
  "news_articles": [{"source": "string", "title": "string", "date": "ISO8601", "content": "string", "url": "string", "is_primary_source": "boolean"}],
  "crunchbase_data": {"total_raised": "number", "funding_rounds": ["array"], "investors": ["array"], "last_valuation": "number | null"},
  "yahoo_finance_data": {"comparable_companies": ["array"], "sector_multiples": "object", "sector_90d_performance": "number"},
  "fred_data": {"fed_funds_rate": "number", "market_conditions": "string", "retrieved_at": "ISO8601"},
  "twitter_data": {
    "sentiment_score": {"positive": "number", "negative": "number", "neutral": "number"},
    "key_quotes": [{"author": "string", "role": "string", "quote": "string", "date": "ISO8601", "url": "string"}]
  },
  "sources_active": ["array"],
  "sources_failed": [{"source": "string", "reason": "string"}],
  "harvested_at": "ISO8601"
}
```

**Failure modes:**
- Any single source fails → `return_exceptions=True` catches it, logs to `sources_failed`, continues
- All sources fail → halt, clear error to frontend
- NewsAPI limit → fall back to RSS only, log warning
- X/Twitter unavailable → skip sentiment, flag, continue

---

### Agent 2: Prospectus Parser (Subagent)

**Single responsibility:** Extract structured financial facts from the S-1 filing.

**Principle 7 — Interleaved thinking:**
After each tool result, subagent uses interleaved thinking to evaluate quality, identify gaps, and decide whether to search again or proceed.

**Input:** Reads `harvester_output` from PostgreSQL via `analysis_id`

**Extracts:**
- Business model summary
- Revenue and growth metrics
- Burn rate and cash runway
- Risk factors (top 10 most material)
- Use of proceeds
- Key people — CEO, CFO, board members
- Comparable company valuations
- Lock-up period details
- Supply/float details — total shares, insider vs public float, greenshoe option
- Demand signals — anchor investors, institutional interest, roadshow signals
- Full funding history
- Whether existing investors are selling (secondary vs primary offering)

**Output written directly to PostgreSQL** (`analyses.parser_output`). Returns `analysis_id` only.

```json
{
  "company_name": "string",
  "business_model": "string",
  "financials": {
    "revenue": "number | null",
    "revenue_growth_yoy": "number | null",
    "burn_rate_monthly": "number | null",
    "cash_runway_months": "number | null"
  },
  "risk_factors": ["array, max 10, each with source citation"],
  "use_of_proceeds": "string",
  "key_people": [{"name": "string", "role": "string", "background": "string"}],
  "comparable_valuations": [{"company": "string", "metric": "string", "value": "number"}],
  "lockup_period_days": "number",
  "float_details": {
    "total_shares_offered": "number",
    "insider_shares": "number",
    "public_float": "number",
    "greenshoe_option": "boolean"
  },
  "demand_signals": {
    "anchor_investors": ["array"],
    "institutional_interest": "high | medium | low | unknown",
    "roadshow_sentiment": "string"
  },
  "funding_history": [{"round": "string", "amount": "number", "date": "ISO8601", "investors": ["array"], "valuation": "number | null"}],
  "offering_type": "primary | secondary | mixed",
  "insider_selling_percentage": "number | null",
  "parsed_at": "ISO8601",
  "data_confidence": "high | medium | low",
  "flagged_sections": [{"section": "string", "reason": "string", "verify_at": "string"}]
}
```

**Failure modes:**
- S-1 not yet filed → flag entire output as preliminary, continue with available data
- Specific section missing → flag with source reference, continue
- LLM extracts implausible number → cross-reference with news, flag if mismatch

---

### Agent 3: Scenario Builder (Subagent)

**Single responsibility:** Build 3 scenarios with probability weightings across 3 time horizons.

**Principle 7 — Interleaved thinking:**
After applying each rule, uses interleaved thinking to evaluate whether the weighting shift is defensible against source data.

**Input:** Reads `parser_output` + `harvester_output` from PostgreSQL via `analysis_id`

**Method:** Rules-based foundation + LLM qualitative adjustment (max ±15%)

**Rules engine:**
- High burn rate + no revenue → pessimistic +10%
- Insider selling >30% → pessimistic +10%
- Lock-up expiry <90 days → pessimistic +5%
- Strong anchor investors → optimistic +10%
- Hot sector (trailing 90d positive) → optimistic +10%
- Low public float (<20%) → optimistic +5% short term
- Primary offering only → optimistic +5%
- High institutional interest → optimistic +10%

**LLM adjustment:** Max ±15% per scenario. Every adjustment must cite a specific source.

**Constraint:** All 3 weightings must sum to exactly 100%.

**Output written directly to PostgreSQL** (`analyses.scenario_output`). Returns `analysis_id` only.

```json
{
  "company_name": "string",
  "complexity_tier": "simple | standard | complex",
  "scenarios": {
    "pessimistic": {
      "probability": "number",
      "drivers": ["array with source citations"],
      "key_risks": ["array with source citations"],
      "price_targets": {"30_days": "number", "90_days": "number", "1_year": "number"},
      "weighting_rationale": "string citing specific data points and sources",
      "rules_applied": ["array of rule names triggered"]
    },
    "realistic": {
      "probability": "number",
      "drivers": ["array with source citations"],
      "key_risks": ["array with source citations"],
      "price_targets": {"30_days": "number", "90_days": "number", "1_year": "number"},
      "weighting_rationale": "string citing specific data points and sources",
      "rules_applied": ["array of rule names triggered"]
    },
    "optimistic": {
      "probability": "number",
      "drivers": ["array with source citations"],
      "key_risks": ["array with source citations"],
      "price_targets": {"30_days": "number", "90_days": "number", "1_year": "number"},
      "weighting_rationale": "string citing specific data points and sources",
      "rules_applied": ["array of rule names triggered"]
    }
  },
  "probability_sum_check": "number (must equal 100)",
  "llm_adjustment_applied": "boolean",
  "llm_adjustment_rationale": "string | null",
  "built_at": "ISO8601"
}
```

**Failure modes:**
- Weightings don't sum to 100 → force normalise, log correction
- LLM adjustment exceeds ±15% → cap at ±15%, log override
- Insufficient data → flag as low confidence, continue

---

### Agent 4: Recommendation Engine (Subagent)

**Single responsibility:** Translate scenarios into one actionable ETF/fund recommendation per scenario.

**Principle 4 — Tool description:**
`etf_lookup` — "Look up ETF details by ticker. Always verify ETF is actively trading before including in recommendation. ETFs can be delisted."

**Input:** Reads `scenario_output` + `parser_output` from PostgreSQL via `analysis_id`

**Output written directly to PostgreSQL** (`analyses.recommendation_output`). Returns `analysis_id` only.

```json
{
  "company_name": "string",
  "recommendations": {
    "pessimistic": {
      "etf_ticker": "string",
      "etf_name": "string",
      "etf_verified_active": "boolean",
      "rationale": "string (one sentence, cites scenario driver)",
      "risk_warning": "string (one sentence)",
      "client_paragraph": "string (300-400 words, neutral tone, no legal jargon)"
    },
    "realistic": {
      "etf_ticker": "string",
      "etf_name": "string",
      "etf_verified_active": "boolean",
      "rationale": "string (one sentence, cites scenario driver)",
      "risk_warning": "string (one sentence)",
      "client_paragraph": "string (300-400 words, neutral tone, no legal jargon)"
    },
    "optimistic": {
      "etf_ticker": "string",
      "etf_name": "string",
      "etf_verified_active": "boolean",
      "rationale": "string (one sentence, cites scenario driver)",
      "risk_warning": "string (one sentence)",
      "client_paragraph": "string (300-400 words, neutral tone, no legal jargon)"
    }
  },
  "plain_english_summary": "string",
  "generated_at": "ISO8601"
}
```

**Failure modes:**
- ETF delisted/unavailable to trade → flag, suggest alternative, re-run
- Rationale exceeds one sentence → regenerate
- Paragraph outside 500 words → regenerate with word count constraint, but don't try to have same length every time; instead return whatever length is appropriate

---

### Agent 5: Judge Agent

**Single responsibility:** Validate full output. Auto-retry failing agents once. Flag unresolved issues in amber with source references. Block export until IFA confirms review.

**Principle 5 — Let agents improve themselves:**
When Judge detects a consistent failure pattern across multiple runs, it:
1. Logs the failure pattern
2. Analyses why the agent is failing
3. Suggests a prompt improvement
4. Logs to `agent_improvements` table for developer review

This creates a self-improving loop over time.

**Principle 7 — Interleaved thinking:**
Uses interleaved thinking after each validation check to assess severity and decide retry vs flag.

**Input:** Reads all agent outputs from PostgreSQL via `analysis_id`

**Validation checklist:**
- [ ] All 3 scenarios present and complete
- [ ] Probability weightings sum to exactly 100%
- [ ] Every risk factor has a named source citation
- [ ] ETF present for each scenario
- [ ] ETF tickers verified as actively trading
- [ ] Risk warning in all 3 recommendations
- [ ] All financial metrics sourced from S-1 or verified news
- [ ] Plain-English summary free of legal jargon
- [ ] Client paragraph up to 500 words
- [ ] All 3 time horizons present per scenario
- [ ] Sentiment score present or flagged with reason
- [ ] No hallucinated names, tickers, or figures
- [ ] All weighting rationales cite specific data points
- [ ] No agent output is null or empty unexpectedly

**Retry logic:**
1. Check fails
2. Auto-retry failing agent once
3. Retry passes → clean output, IFA sees nothing
4. Retry fails → amber flag with exact source reference, export locked
5. IFA confirms each flag → export unlocks

**Self-improvement log:**
```python
improvement_suggestion = {
  "agent": "prospectus_parser",
  "failure_pattern": "burn_rate consistently null despite being in filing",
  "suggested_prompt_addition": "Look for 'monthly operating expenses' and 'cash used in operations' as alternative burn rate signals",
  "detected_at": "ISO8601",
  "occurrence_count": "number"
}
# Write to agent_improvements table
```

**Flag format:**
```
[Section Name] — Low Confidence
Reason: [specific reason]
Verify at: [exact source and page/section reference]
Action required: Review before presenting to client.
```

**Output written to PostgreSQL** (`analyses.judge_output`):
```json
{
  "validation_passed": "boolean",
  "flags": [
    {
      "flag_id": "uuid",
      "section": "string",
      "severity": "amber | red",
      "reason": "string",
      "source_reference": "string",
      "retry_attempted": "boolean",
      "retry_passed": "boolean",
      "improvement_suggestion": "string | null"
    }
  ],
  "export_locked": "boolean",
  "ifa_confirmed_flags": ["array of confirmed flag_ids"],
  "validated_at": "ISO8601"
}
```

---

## Data Schema — Database (Docker PostgreSQL)

### Table: analyses
```sql
CREATE TABLE analyses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  custom_name VARCHAR(255),
  company_name VARCHAR(255) NOT NULL,
  complexity_tier VARCHAR(20) DEFAULT 'standard',
  status VARCHAR(50) DEFAULT 'pending',
  last_completed_agent VARCHAR(100),
  lead_plan JSONB,
  harvester_output JSONB,
  parser_output JSONB,
  scenario_output JSONB,
  recommendation_output JSONB,
  judge_output JSONB,
  final_report JSONB,
  flags JSONB,
  ifa_confirmed_flags JSONB,
  export_locked BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT NOW(),
  saved BOOLEAN DEFAULT false,
  saved_at TIMESTAMP
);
```

### Table: agent_runs
```sql
CREATE TABLE agent_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id UUID REFERENCES analyses(id),
  agent_name VARCHAR(100),
  status VARCHAR(50),
  input_reference VARCHAR(255),
  output_reference VARCHAR(255),
  retry_count INTEGER DEFAULT 0,
  error_message TEXT,
  token_count INTEGER,
  tool_calls_count INTEGER,
  started_at TIMESTAMP,
  completed_at TIMESTAMP
);
```

### Table: checkpoints
```sql
CREATE TABLE checkpoints (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id UUID REFERENCES analyses(id),
  agent_name VARCHAR(100),
  checkpoint_data JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);
```

### Table: agent_improvements
```sql
CREATE TABLE agent_improvements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_name VARCHAR(100),
  failure_pattern TEXT,
  suggested_prompt_addition TEXT,
  occurrence_count INTEGER DEFAULT 1,
  detected_at TIMESTAMP DEFAULT NOW(),
  applied BOOLEAN DEFAULT false,
  applied_at TIMESTAMP
);
```

---

## 🖥️ Frontend — React + shadcn/ui

**Single page application. Runs on localhost:3000.**

**Left panel (30% width):**
- Company name input (shadcn Input)
- Generate Analysis button (shadcn Button)
- Complexity badge — auto-displays after input (Simple / Standard / Complex)
- Real-time agent progress via WebSocket:
  - ⬜ / ⏳ / ✅ / ❌ Lead Orchestrator
  - ⬜ / ⏳ / ✅ / ❌ Data Harvester
  - ⬜ / ⏳ / ✅ / ❌ Prospectus Parser
  - ⬜ / ⏳ / ✅ / ❌ Scenario Builder
  - ⬜ / ⏳ / ✅ / ❌ Recommendation Engine
  - ⬜ / ⏳ / ✅ / ❌ Judge Agent
- Active tool calls shown per agent ("Fetching SEC EDGAR... Crunchbase... NewsAPI...")
- Amber flags listed with source references
- Confirm flags button (unlocks export)

**Right panel (70% width):**
Three scenario cards side by side (shadcn Card):

| 🔴 Pessimistic X% | 🟡 Realistic X% | 🟢 Optimistic X% |
|---|---|---|
| Drivers (sourced) | Drivers (sourced) | Drivers (sourced) |
| Key risks (sourced) | Key risks (sourced) | Key risks (sourced) |
| 30d / 90d / 1yr | 30d / 90d / 1yr | 30d / 90d / 1yr |
| ETF: ticker | ETF: ticker | ETF: ticker |
| Rationale | Rationale | Rationale |
| ⚠️ Risk warning | ⚠️ Risk warning | ⚠️ Risk warning |

**Below cards:**
- Plain-English prospectus summary (collapsible)
- X/Twitter sentiment score bar
- Client-forwardable paragraph (copyable)
- Data sources with retrieval timestamps (collapsible)
- Export Summary PDF button
- Export Full Report PDF button
- Save Report → custom name dialog

**shadcn components:**
Card, Button, Input, Progress, Badge, Alert, Dialog, Collapsible, Separator, Tooltip (source citations on hover)

---

## 📄 PDF Export

**Export Summary (one page):**
- Company name + IPO date
- Three scenario cards with probability weightings
- Price targets table (30d / 90d / 1yr per scenario)
- One ETF recommendation per scenario with risk warning
- Data sources footer with retrieval timestamps
- Timestamp + disclaimer

**Export Full Report (multi-page):**
- Cover page — company name, analysis date, disclaimer
- Executive summary
- Section 1: Company Overview (plain-English prospectus summary)
- Section 2: Market Context (FRED macro data, sector performance)
- Section 3: Scenario Analysis (full detail with weighting rationale + source citations)
- Section 4: Recommendations (ETF per scenario + risk warnings)
- Section 5: Supporting Evidence (key X/Twitter quotes with attribution)
- Section 6: Data Sources (all active sources with retrieval timestamps)
- Disclaimer page

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.13 |
| Agent framework | LangGraph |
| Backend API | FastAPI |
| Async execution | asyncio (parallel tool calls) |
| Frontend | React + shadcn/ui |
| Real-time updates | WebSocket (FastAPI) |
| Database | PostgreSQL (Docker) |
| LLM inference | Open weights model (to be confirmed) via cloud elastic |
| Containerisation | Docker + docker-compose |
| PDF generation | WeasyPrint or ReportLab |
| News ingestion | NewsAPI + RSS (feedparser) |
| Financial data | yfinance, FRED API |
| Company data | Crunchbase API |
| Social data | X/Twitter API v2 |
| SEC filings | SEC EDGAR API |
| Testing | pytest |
| CI/CD | GitHub Actions |
| Version control | Git/GitHub |

**No new tools unless essential.**

---

## 🚀 Local Setup

```bash
docker-compose up    # starts everything
docker-compose down  # stops everything
```

Services:
- Frontend: localhost:3000
- Backend API: localhost:8000
- PostgreSQL: localhost:5432

Data persists via Docker volume. Pipeline resumes from `last_completed_agent` on failure — never restarts from zero.

---

## ✅ Tests — Write Before Any Code

### True Positive Tests:
1. SpaceX — parser extracts revenue correctly from S-1
2. SpaceX — high insider selling → pessimistic weighting increases
3. SpaceX — anchor investor present → optimistic weighting increases
4. SpaceX — probability weightings sum to 100%
5. SpaceX — all 3 time horizons present
6. SpaceX — ETF recommendation present for all 3 scenarios
7. SpaceX — risk warning in all 3 recommendations
8. SpaceX — client paragraph between 300-400 words
9. SpaceX — plain-English summary free of legal jargon
10. SpaceX — Judge Agent passes without flags
11. SpaceX — all 7 sources fetched in parallel (verify via agent_runs timestamps)
12. SpaceX — Lead Orchestrator saves plan to checkpoints before spawning
13. SpaceX — classified as "complex", all 7 sources activated
14. SpaceX — each agent writes to PostgreSQL, passes analysis_id only

### True Negative Tests:
15. Clean IPO — no insider selling → pessimistic stays baseline
16. Clean IPO — primary offering only → no secondary selling flag
17. Clean IPO — strong institutional interest → optimistic increases
18. Clean IPO — Judge passes with no flags
19. Clean IPO — export unlocked without IFA confirmation
20. Simple IPO — classified as "simple", only 3 sources activated

### Failure Mode Tests:
21. SEC EDGAR down → flags, continues with available data
22. Crunchbase down → funding section flagged in amber with source reference
23. X/Twitter down → sentiment skipped, flagged, report still generates
24. LLM returns implausible burn rate → cross-reference triggers, flag raised
25. Probability weightings sum to 99% → normalisation applied, logged

### Resume + Checkpoint Tests:
26. Pipeline fails at Agent 3 → restart with same analysis_id → resumes from Agent 3
27. Context window approaches limit → Lead Orchestrator retrieves plan from checkpoints
28. Agent retry succeeds → clean report, no flag shown
29. Agent retry fails → amber flag with source reference, export locked

### Edge Case Tests:
30. No S-1 filed yet → all sections flagged as preliminary
31. Company name typo → clear error, prompts correction
32. Judge detects consistent failure → improvement logged to agent_improvements
33. IFA confirms all flags → export unlocks
34. Client paragraph 250 words → regeneration triggered
35. Client paragraph 450 words → truncation triggered
36. ETF delisted → flag raised, alternative suggested
37. All 7 sources unavailable → system halts, clear error to frontend
38. Two analyses queued → second waits, first completes, second starts

### Ambiguous Case Tests:
39. **Conflicting signals — high burn + strong anchor investors:** Company has monthly burn of $50M with 6 months runway (pessimistic +10%) AND confirmed Sequoia anchor (optimistic +10%). Expected: rules engine applies both, LLM adjudicates net effect, weighting rationale cites both signals explicitly, no silent cancellation.
40. **Insider selling exactly at threshold (30%):** Insider selling is 30.0% of offering — sits exactly on the pessimistic trigger boundary. Expected: system treats ≥30% as trigger, pessimistic +10% applied, boundary value documented in `rules_applied`.
41. **S-1 filed but 40%+ of financial section redacted:** SEC EDGAR returns filing with `[REDACTED]` across revenue, burn rate, and use of proceeds. Expected: parser marks all redacted fields as `null`, `data_confidence = "low"`, `flagged_sections` lists each with "Source: SEC EDGAR S-1 — section redacted". Judge flags amber, export locked.
42. **Roadshow announced but no S-1 filed yet:** News confirms roadshow in progress, but EDGAR returns no S-1 for the ticker. Expected: system enters preliminary mode — parser output fully flagged, scenarios built from news and Crunchbase only, every output section carries "Preliminary — S-1 not yet available" label.
43. **Hot sector + rising interest rates (conflicting macro signals):** Sector 90-day performance is +18% (optimistic +10%) but FRED shows fed funds rate at 5.5% and rising (macro headwind). Expected: LLM adjustment acknowledges rate environment in `weighting_rationale`, does not silently ignore FRED data.
44. **Ticker found in EDGAR but matches wrong company:** Ticker submitted returns a valid EDGAR filing, but the company name in the filing doesn't match the input. Expected: system surfaces mismatch — "Filing found for [TICKER] but company name is [FILING_COMPANY], not [INPUT_COMPANY]. Confirm or re-enter ticker." Pipeline pauses, does not proceed.
45. **All optimistic rules trigger simultaneously:** Primary offering, strong anchor investors, hot sector, high institutional interest, low public float all present. Expected: optimistic weighting hits LLM adjustment cap (max ±15% on top of rules), does not exceed bounds, `probability_sum_check = 100`.
46. **Prospectus Parser returns null output on first run, valid output on retry:** First run: silent crash, null written to DB. Retry: valid JSON written to DB. Expected: pipeline continues after retry, no amber flag shown to IFA, retry logged in `agent_runs` with `retry_count = 1`.

---

## 🏗️ Build Phase Agent Rules (Cursor Workflow)

These govern how you interact with Cursor when building this product. Separate from the product agents above — these are the coding agents.

**Three roles. Never mix in one prompt.**

### Planner Agent
- **Job:** Read `architecture.md`, explore the codebase, produce a task list
- **Output:** `.cursor/plans/tasks.md` — ordered list of atomic tasks, one per line
- **Rules:**
  - Never writes code
  - Never makes file edits
  - One Cursor conversation per planning session — start fresh each time
  - If it asks clarifying questions, answer them before it produces the task list
- **Prompt template:**
  > "Read `.cursor/plans/architecture.md` and the current codebase. Produce a task list in `.cursor/plans/tasks.md`. Each task must be atomic — one file, one function, one responsibility. Do not write any code. Do not make any edits. Output the task list only."

### Worker Agent
- **Job:** Pick up one task from `tasks.md`, implement it, stop
- **Output:** Code — one task completed per conversation
- **Rules:**
  - One task per Cursor conversation — never multi-task
  - If it deviates from the architecture doc, stop it immediately and start fresh
  - If it repeats the same mistake twice → start a new conversation, don't keep correcting
  - Always paste the relevant section of `architecture.md` into context before the task prompt
- **Prompt template:**
  > "Here is the architecture context: [paste relevant section]. Your task: [single task from tasks.md]. Implement this only. Do not modify other files. Do not add features not in the architecture doc."

### Judge Agent
- **Job:** Run the test suite, read results, return a pass/fail verdict
- **Output:** Verdict — pass (move to next task) or fail (return to Worker with specific failure)
- **Rules:**
  - Runs `pytest` — does not interpret test intent, reads actual output
  - Returns exact failing test name and error message to Worker
  - Never fixes code itself — verdict only
  - CI/CD gate: all tests must pass in GitHub Actions before any task is marked complete
- **Prompt template:**
  > "Run `pytest tests/` and report the result. If passing: 'PASS — [n] tests passed.' If failing: 'FAIL — [test_name]: [exact error message].' Do not fix anything. Report only."

**Session discipline:**
- Start a new Cursor conversation when switching between Planner / Worker / Judge roles
- Save all plans and task lists to `.cursor/plans/` — never in root
- Never open Cursor without reading `architecture.md` first in that session
- If a Worker agent is stuck after two attempts on the same task → escalate to a new Planner session to rebreak the task into smaller pieces

---



| Failure | Behaviour |
|---|---|
| Single API down | Parallel fetch catches it → flag → continue |
| All APIs down | Halt → clear error |
| LLM hallucination | Interleaved thinking cross-references → flag if mismatch |
| Probability sum ≠ 100% | Auto-normalise → log |
| Agent retry fails | Amber flag → source reference → export locked |
| Pipeline fails mid-run | Resume from last_completed_agent checkpoint |
| Context window overflow | Lead Orchestrator retrieves plan from checkpoints table |
| IFA confirms flags | Export unlocks |
| ETF delisted | Flag → suggest alternative |
| Consistent agent failure | Judge logs improvement to agent_improvements |

---

## 📊 Evaluation Criteria

**LLM-as-judge eval runs after every pipeline completion (scores 0.0-1.0):**
- Factual accuracy — claims match sources?
- Citation accuracy — source references exist and match claims?
- Completeness — all sections present?
- Source quality — primary sources preferred over secondary?
- Tool efficiency — tool calls within complexity tier bounds?
- Scenario coherence — scenarios internally consistent and distinct?

**Good output:**
- All 6 agents complete without flags
- Probability weightings sum to 100%
- All metrics traceable to named primary source
- ETF recommendation defensible to compliance review
- Client paragraph readable by non-financial person
- Tool calls within complexity tier bounds
- Eval agent scores ≥ 0.8 across all rubric dimensions

**Bad output:**
- Any hallucinated figure with no source
- Probability weightings don't sum to 100%
- Missing time horizon in any scenario
- Paragraph outside 300-400 words
- Export unlocked despite unconfirmed flags
- Tool calls exceed complexity tier maximum
- Eval agent scores < 0.6 on any dimension
- Pipeline restarts from zero on failure (checkpoint not used)

---

## 🔁 Prompt Engineering Rules (Embedded in All Agent Prompts)

All agent prompts encode these heuristics — frameworks for good behaviour, not rigid rules:

1. Examine all available tools first before deciding which to use
2. Match tool to intent — don't use generic when specific exists
3. Start with short broad queries (1-3 words), narrow progressively
4. Prefer primary sources (SEC EDGAR) over secondary (news aggregators)
5. Cite every claim — no assertion without a named source
6. Flag uncertainty explicitly — never silently accept implausible values
7. Respect task boundaries — don't duplicate work assigned to other subagents
8. Scale tool calls to complexity — 3-5 for simple, 10-15 for complex

---

*Architecture Doc v2.1 complete. Paste into `.cursor/plans/architecture.md` before opening Cursor.*
*Use Plan Mode (Shift+Tab) at the start of every Cursor session.*
*Write tests before agents touch the codebase.*
*All 8 Anthropic multi-agent principles applied throughout.*