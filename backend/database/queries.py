import json
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
        return await connection.fetchrow(
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


async def save_judge_output(analysis_id: str, output: dict[str, Any]) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET judge_output = $2
            WHERE id = $1
            """,
            analysis_id,
            _to_jsonb(output),
        )
    finally:
        await release_connection(connection)


async def save_final_report(analysis_id: str, report: dict[str, Any]) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET final_report = $2
            WHERE id = $1
            """,
            analysis_id,
            _to_jsonb(report),
        )
    finally:
        await release_connection(connection)


async def set_flags_and_export_lock(
    analysis_id: str,
    flags: list[dict[str, Any]],
    export_locked: bool,
) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET flags = $2, export_locked = $3
            WHERE id = $1
            """,
            analysis_id,
            _to_jsonb(flags),
            export_locked,
        )
    finally:
        await release_connection(connection)


async def set_ifa_confirmed_flags(
    analysis_id: str,
    confirmed_flags: list[str],
    export_locked: bool,
) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE analyses
            SET ifa_confirmed_flags = $2, export_locked = $3
            WHERE id = $1
            """,
            analysis_id,
            _to_jsonb(confirmed_flags),
            export_locked,
        )
    finally:
        await release_connection(connection)
