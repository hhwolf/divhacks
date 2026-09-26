"""Adaptive Room Planner API. Runs fully offline in mock mode; see app/config.py for the env vars that enable live services."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.catalog import FIXTURES_DIR
from app.config import REPO_ROOT, Settings
from app.deps import AppContext
from app.routers import agent, furniture, health, layouts, rent, rooms, webhooks


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Adaptive Room Planner API", version=health.VERSION)
    app.state.ctx = AppContext.build(settings)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    for r in (health.router, rooms.router, layouts.router, furniture.router, rent.router, agent.router, webhooks.router):
        app.include_router(r)

    @app.get("/fixtures/listings/desk", include_in_schema=False)
    async def desk_listing() -> FileResponse:
        return FileResponse(FIXTURES_DIR / "listings" / "desk.html", media_type="text/html")

    app.mount("/fixtures/listings", StaticFiles(directory=FIXTURES_DIR / "listings"), name="listings")
    app.mount("/assets", StaticFiles(directory=REPO_ROOT / "assets"), name="assets")
    return app


app = create_app()
