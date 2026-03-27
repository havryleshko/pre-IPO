from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes_analysis import router as analysis_router
from backend.api.websocket_progress import router as websocket_progress_router
from backend.config.settings import get_settings
from backend.database.connection import close_pool, get_pool


def create_app() -> FastAPI:
    app = FastAPI(title="pre-IPO")
    settings = get_settings()
    origins = settings.cors_origins if isinstance(settings.cors_origins, list) else [str(settings.cors_origins)]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

    @app.on_event("startup")
    async def startup_event() -> None:
        await get_pool()

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        await close_pool()

    app.include_router(analysis_router)
    app.include_router(websocket_progress_router)
    return app


app = create_app()
