import errno
import logging

import asyncpg

from backend.config.settings import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


def _normalize_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def get_pool() -> asyncpg.Pool:
    global _pool

    if _pool is None:
        settings = get_settings()
        try:
            _pool = await asyncpg.create_pool(
                dsn=_normalize_database_url(settings.database_url),
                command_timeout=settings.request_timeout_seconds,
                min_size=1,
                max_size=10,
            )
        except OSError as exc:
            if exc.errno == errno.ECONNREFUSED:
                logger.error(
                    "PostgreSQL connection refused. Start Postgres first, for example: ./run-local.sh"
                )
            raise
        logger.info("Initialized PostgreSQL connection pool")

    return _pool


async def close_pool() -> None:
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Closed PostgreSQL connection pool")


async def acquire_connection() -> asyncpg.Connection:
    pool = await get_pool()
    return await pool.acquire()


async def release_connection(connection: asyncpg.Connection) -> None:
    pool = await get_pool()
    await pool.release(connection)
