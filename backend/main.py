from fastapi import FastAPI

from backend.api.routes_analysis import router as analysis_router
from backend.api.routes_export import router as export_router
from backend.api.websocket_progress import router as websocket_progress_router
from backend.database.connection import close_pool, get_pool


def create_app() -> FastAPI:
    app = FastAPI(title="pre-IPO")

    @app.on_event("startup")
    async def startup_event() -> None:
        await get_pool()

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        await close_pool()

    app.include_router(analysis_router)
    app.include_router(export_router)
    app.include_router(websocket_progress_router)
    return app


app = create_app()
