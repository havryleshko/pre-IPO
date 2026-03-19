import json
from typing import Any

import asyncpg

from backend.database.connection import acquire_connection, release_connection


async def save_checkpoint(
    analysis_id: str,
    agent_name: str,
    checkpoint_data: dict[str, Any],
) -> asyncpg.Record:
    connection = await acquire_connection()
    try:
        return await connection.fetchrow(
            """
            INSERT INTO checkpoints (analysis_id, agent_name, checkpoint_data)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            analysis_id,
            agent_name,
            json.dumps(checkpoint_data),
        )
    finally:
        await release_connection(connection)


async def load_latest_checkpoint(
    analysis_id: str,
    agent_name: str | None = None,
) -> asyncpg.Record | None:
    connection = await acquire_connection()
    try:
        if agent_name is None:
            return await connection.fetchrow(
                """
                SELECT *
                FROM checkpoints
                WHERE analysis_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                analysis_id,
            )

        return await connection.fetchrow(
            """
            SELECT *
            FROM checkpoints
            WHERE analysis_id = $1 AND agent_name = $2
            ORDER BY created_at DESC
            LIMIT 1
            """,
            analysis_id,
            agent_name,
        )
    finally:
        await release_connection(connection)
