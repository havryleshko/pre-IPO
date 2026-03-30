from backend.database.queries import update_analysis_status


async def set_analysis_pending(analysis_id: str) -> str:
    return await update_analysis_status(analysis_id=analysis_id, status="pending")


async def set_analysis_running(analysis_id: str, last_completed_agent: str | None = None) -> str:
    return await update_analysis_status(
        analysis_id=analysis_id,
        status="running",
        last_completed_agent=last_completed_agent,
    )


async def mark_agent_completed(analysis_id: str, agent_name: str) -> str:
    return await update_analysis_status(
        analysis_id=analysis_id,
        status="running",
        last_completed_agent=agent_name,
    )


async def set_analysis_completed(analysis_id: str, last_completed_agent: str | None = None) -> str:
    return await update_analysis_status(
        analysis_id=analysis_id,
        status="completed",
        last_completed_agent=last_completed_agent,
    )


async def set_analysis_completed_with_flags(
    analysis_id: str,
    last_completed_agent: str | None = None,
) -> str:
    return await update_analysis_status(
        analysis_id=analysis_id,
        status="completed_with_flags",
        last_completed_agent=last_completed_agent,
    )


async def set_analysis_failed(analysis_id: str, last_completed_agent: str | None = None) -> str:
    return await update_analysis_status(
        analysis_id=analysis_id,
        status="failed",
        last_completed_agent=last_completed_agent,
    )
