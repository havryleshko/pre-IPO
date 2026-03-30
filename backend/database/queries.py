import json
from datetime import date
from typing import Any

import asyncpg

from backend.database.connection import acquire_connection, release_connection
from backend.models.analysis import AnalysisComplexityTier


def _to_jsonb(value: Any) -> str:
    return json.dumps(value)


_JSON_COLUMNS: tuple[str, ...] = (
    "lead_plan",
    "harvester_output",
    "parser_output",
    "scenario_output",
    "recommendation_output",
    "judge_output",
    "final_report",
    "flags",
    "ifa_confirmed_flags",
)


def _decode_json_columns(row: Any) -> dict[str, Any]:
    data = dict(row)
    for column in _JSON_COLUMNS:
        raw = data.get(column)
        if not isinstance(raw, str):
            continue
        try:
            data[column] = json.loads(raw)
        except json.JSONDecodeError:
            continue
    return data


async def create_analysis(
    company_name: str,
    custom_name: str | None = None,
    complexity_tier: str = "standard",
) -> asyncpg.Record:
    connection = await acquire_connection()
    try:
        row = await connection.fetchrow(
            """
            INSERT INTO analyses (company_name, custom_name, complexity_tier, status)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            company_name,
            custom_name,
            complexity_tier,
            "pending",
        )
        if row is None:
            raise RuntimeError("create_analysis: INSERT returned no row")
        return row
    finally:
        await release_connection(connection)


async def get_analysis_by_id(analysis_id: str) -> dict[str, Any] | None:
    connection = await acquire_connection()
    try:
        row = await connection.fetchrow(
            """
            SELECT *
            FROM analyses
            WHERE id = $1
            """,
            analysis_id,
        )
        if row is None:
            return None
        return _decode_json_columns(row)
    finally:
        await release_connection(connection)


async def set_analysis_ticker_and_ipo_date(
    analysis_id: str,
    ticker: str | None,
    ipo_date: date | None,
) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET ticker = $2, ipo_date = $3
            WHERE id = $1
            """,
            analysis_id,
            ticker,
            ipo_date,
        )
    finally:
        await release_connection(connection)


async def get_analysis_ticker_and_ipo_date(
    analysis_id: str,
) -> tuple[str | None, date | None] | None:
    connection = await acquire_connection()
    try:
        row = await connection.fetchrow(
            """
            SELECT ticker, ipo_date
            FROM analyses
            WHERE id = $1
            """,
            analysis_id,
        )
        if row is None:
            return None
        return row["ticker"], row["ipo_date"]
    finally:
        await release_connection(connection)


async def update_analysis_status(
    analysis_id: str,
    status: str,
    last_completed_agent: str | None = None,
) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET status = $2, last_completed_agent = $3
            WHERE id = $1
            """,
            analysis_id,
            status,
            last_completed_agent,
        )
    finally:
        await release_connection(connection)

async def set_analysis_complexity_tier(analysis_id: str, complexity_tier: AnalysisComplexityTier) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET complexity_tier = $2
            WHERE id = $1
            """,
            analysis_id,
            complexity_tier,
        )
    finally:
        await release_connection(connection)

async def set_analysis_active_sources(analysis_id: str, active_sources: list[str]) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET lead_plan = COALESCE(lead_plan, '{}'::jsonb) || jsonb_build_object('active_sources', $2::jsonb)
            WHERE id = $1
            """,
            analysis_id,
            _to_jsonb(active_sources),
        )
    finally:
        await release_connection(connection)


async def save_lead_plan(analysis_id: str, lead_plan: dict[str, Any]) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET lead_plan = $2
            WHERE id = $1
            """,
            analysis_id,
            _to_jsonb(lead_plan),
        )
    finally:
        await release_connection(connection)


async def save_harvester_output(analysis_id: str, output: dict[str, Any]) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET harvester_output = $2
            WHERE id = $1
            """,
            analysis_id,
            _to_jsonb(output),
        )
    finally:
        await release_connection(connection)


async def save_parser_output(analysis_id: str, output: dict[str, Any]) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET parser_output = $2
            WHERE id = $1
            """,
            analysis_id,
            _to_jsonb(output),
        )
    finally:
        await release_connection(connection)


async def save_scenario_output(analysis_id: str, output: dict[str, Any]) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET scenario_output = $2
            WHERE id = $1
            """,
            analysis_id,
            _to_jsonb(output),
        )
    finally:
        await release_connection(connection)


async def save_recommendation_output(analysis_id: str, output: dict[str, Any]) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET recommendation_output = $2
            WHERE id = $1
            """,
            analysis_id,
            _to_jsonb(output),
        )
    finally:
        await release_connection(connection)


async def save_judge_bundle(
    analysis_id: str,
    judge_output: dict[str, Any],
    flags: list[str],
) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET judge_output = $2, flags = $3
            WHERE id = $1
            """,
            analysis_id,
            _to_jsonb(judge_output),
            _to_jsonb(flags),
        )
    finally:
        await release_connection(connection)


async def save_final_report(analysis_id: str, output: dict[str, Any]) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET final_report = $2
            WHERE id = $1
            """,
            analysis_id,
            _to_jsonb(output),
        )
    finally:
        await release_connection(connection)


async def save_investor_brief(analysis_id: str, output: dict[str, Any]) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET investor_brief = $2
            WHERE id = $1
            """,
            analysis_id,
            _to_jsonb(output),
        )
    finally:
        await release_connection(connection)


async def upsert_demo_analysis_payload(row: dict[str, Any]) -> str:
    connection = await acquire_connection()
    try:
        existing = await connection.fetchrow(
            """
            SELECT id
            FROM analyses
            WHERE company_name = $1
            """,
            row["company_name"],
        )
        if existing is not None:
            await connection.execute(
                """
                UPDATE analyses
                SET
                    custom_name = COALESCE($2, custom_name),
                    complexity_tier = $3,
                    status = $4,
                    last_completed_agent = $5,
                    ticker = $6,
                    ipo_date = $7,
                    lead_plan = $8,
                    harvester_output = $9,
                    parser_output = $10,
                    scenario_output = $11,
                    investor_brief = $12,
                    recommendation_output = $13,
                    judge_output = $14,
                    flags = $15
                WHERE id = $1
                """,
                str(existing["id"]),
                row["custom_name"],
                row["complexity_tier"],
                row["status"],
                row["last_completed_agent"],
                row["ticker"],
                row["ipo_date"],
                _to_jsonb(row["lead_plan"]),
                _to_jsonb(row["harvester_output"]),
                _to_jsonb(row["parser_output"]),
                _to_jsonb(row["scenario_output"]),
                _to_jsonb(row["investor_brief"]),
                _to_jsonb(row["recommendation_output"]),
                _to_jsonb(row["judge_output"]),
                _to_jsonb(row["flags"]),
            )
            return str(existing["id"])
        new_id = await connection.fetchval(
            """
            INSERT INTO analyses (
                company_name,
                custom_name,
                complexity_tier,
                status,
                last_completed_agent,
                ticker,
                ipo_date,
                lead_plan,
                harvester_output,
                parser_output,
                scenario_output,
                investor_brief,
                recommendation_output,
                judge_output,
                flags
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
            )
            RETURNING id
            """,
            row["company_name"],
            row["custom_name"],
            row["complexity_tier"],
            row["status"],
            row["last_completed_agent"],
            row["ticker"],
            row["ipo_date"],
            _to_jsonb(row["lead_plan"]),
            _to_jsonb(row["harvester_output"]),
            _to_jsonb(row["parser_output"]),
            _to_jsonb(row["scenario_output"]),
            _to_jsonb(row["investor_brief"]),
            _to_jsonb(row["recommendation_output"]),
            _to_jsonb(row["judge_output"]),
            _to_jsonb(row["flags"]),
        )
        if new_id is None:
            raise RuntimeError("upsert_demo_analysis_payload: INSERT returned no id")
        return str(new_id)
    finally:
        await release_connection(connection)
