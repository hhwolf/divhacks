"""FitCheck API. Runs fully offline in mock mode; see app/config.py for the env vars that enable live services."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.catalog import FIXTURES_DIR
from app.config import REPO_ROOT, Settings
from app.deps import AppContext
from app.routers import agent, furniture, health, layouts, rent, rooms, webhooks, payments, evidence
from app.deps import get_ctx
from fastapi import Depends


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.payments_mode not in ("demo", "stripe_test"):
        raise ValueError("PAYMENTS_MODE supports demo or stripe_test only; live payments are disabled")
    if settings.stripe_secret_key and not settings.stripe_secret_key.startswith("sk_test_"):
        raise ValueError("Only Stripe test secret keys are accepted; live payments are disabled")
    if any(o.strip() == "*" for o in settings.allowed_origins.split(",")):
        raise ValueError("ALLOWED_ORIGINS must list explicit web origins")
    app = FastAPI(title="FitCheck API", version=health.VERSION)
    app.state.ctx = AppContext.build(settings)
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()], allow_methods=["*"], allow_headers=["*"])
    for r in (health.router, rooms.router, rooms.setup_router, layouts.router, furniture.router, rent.router, payments.router, evidence.router, agent.router, webhooks.router):
        app.include_router(r)

    @app.post("/session/link-phone")
    async def link_phone(ctx=Depends(get_ctx)) -> dict:
        from fastapi import HTTPException
        if not ctx.principal.authenticated or not ctx.principal.phone:
            raise HTTPException(409, "Verify your phone in Supabase Auth before linking Photon")
        owner = ctx.principal.id
        existing = await app.state.ctx.repo.list("phone_links", phone=ctx.principal.phone)
        if existing and existing[0]["userId"] != owner:
            raise HTTPException(409, "Phone already linked")
        if not existing:
            await ctx.repo.insert("phone_links", {"id": owner, "userId": owner, "phone": ctx.principal.phone})
        return {"linked": True}

    @app.get("/session")
    async def session(ctx=Depends(get_ctx)) -> dict:
        return {"userId": ctx.principal.id, "authenticated": ctx.principal.authenticated,
                "mode": "private" if ctx.principal.authenticated else "demo",
                "payments": "stripe_test" if ctx.principal.authenticated and ctx.settings.payments_mode == "stripe_test" else "demo",
                "livePaymentsEnabled": False}

    @app.get("/fixtures/listings/desk", include_in_schema=False)
    async def desk_listing() -> FileResponse:
        return FileResponse(FIXTURES_DIR / "listings" / "desk.html", media_type="text/html")

    app.mount("/fixtures/listings", StaticFiles(directory=FIXTURES_DIR / "listings"), name="listings")
    app.mount("/assets", StaticFiles(directory=REPO_ROOT / "assets"), name="assets")
    return app


app = create_app()
