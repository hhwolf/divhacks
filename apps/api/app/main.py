"""Adaptive Room Planner API. Runs fully offline in mock mode; see app/config.py for the secrets that enable live services."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.catalog import FIXTURES_DIR
from app.config import REPO_ROOT, VERSION, Settings
from app.deps import AppContext
from app.routers import agent, furniture, health, layouts, rent, rooms, validation
from app.services.blob import LocalBlob


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    missing = settings.missing_required()
    if missing:
        raise RuntimeError(f"MOCK_MODE is off but these required secrets are not set: {', '.join(missing)}")
    app = FastAPI(title="Adaptive Room Planner API", version=VERSION)
    app.state.ctx = AppContext.build(settings)
    app.add_middleware(CORSMiddleware, allow_methods=["*"], allow_headers=["*"], **settings.cors)  # type: ignore[arg-type]
    for r in (health.router, rooms.router, layouts.router, furniture.router, validation.router, agent.router, rent.router):
        app.include_router(r)

    @app.get("/fixtures/listings/desk", include_in_schema=False)
    async def desk_listing() -> FileResponse:
        return FileResponse(FIXTURES_DIR / "listings" / "desk.html", media_type="text/html")

    app.mount("/fixtures/listings", StaticFiles(directory=FIXTURES_DIR / "listings"), name="listings")
    app.mount("/assets", StaticFiles(directory=REPO_ROOT / "assets"), name="assets")
    if isinstance(app.state.ctx.blob, LocalBlob):  # mock/dev file storage; Vercel Blob URLs are absolute
        app.mount("/blob", StaticFiles(directory=app.state.ctx.blob.root), name="blob")
    return app


app = create_app()
