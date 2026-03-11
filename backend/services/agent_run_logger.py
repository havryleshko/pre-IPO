from typing import Any

from backend.database.connection import acquire_connection, release_connection


async def log_agent_run_start(
    analysis_id: str,
    agent_name: str,
    input_reference: str | None = None,
    retry_count: int = 0,
) -> Any:
    connection = await acquire_connection()
    try:
        return await connection.fetchrow(
            """
            INSERT INTO agent_runs (
                analysis_id,
                agent_name,
                status,
                input_reference,
                retry_count,
                started_at
            )
            VALUES ($1, $2, $3, $4, $5, NOW())
            RETURNING *
            """,
            analysis_id,
            agent_name,
            "running",
            input_reference,
            retry_count,
        )
    finally:
        await release_connection(connection)


async def log_agent_run_completed(
    run_id: str,
    output_reference: str | None = None,
    token_count: int | None = None,
    tool_calls_count: int | None = None,
) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE agent_runs
            SET status = $2,
                output_reference = $3,
                token_count = $4,
                tool_calls_count = $5,
                completed_at = NOW()
            WHERE id = $1
            """,
            run_id,
            "completed",
            output_reference,
            token_count,
            tool_calls_count,
        )
    finally:
        await release_connection(connection)


async def log_agent_run_failed(
    run_id: str,
    error_message: str,
    token_count: int | None = None,
    tool_calls_count: int | None = None,
) -> str:
    connection = await acquire_connection()
    try:
        return await connection.execute(
            """
            UPDATE agent_runs
            SET status = $2,
                error_message = $3,
                token_count = $4,
                tool_calls_count = $5,
                completed_at = NOW()
            WHERE id = $1
            """,
            run_id,
            "failed",
            error_message,
            token_count,
            tool_calls_count,
        )
    finally:
        await release_connection(connection)
