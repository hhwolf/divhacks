from fastapi import APIRouter, Depends

from app.deps import AppContext, get_ctx

router = APIRouter(tags=["health"])
VERSION = "0.1.0"


@router.get("/health")
async def health(ctx: AppContext = Depends(get_ctx)) -> dict:
    s = ctx.settings
    integrations = {
        "gemini": "live" if s.gemini_live else "mock",
        "backboard": "live" if s.backboard_live else "mock",
        "photon": "live" if s.photon_live else "mock",
        "supabase": s.store_kind,
        "payments": "record-only",
    }
    states = {integrations["gemini"], integrations["backboard"], integrations["photon"]}
    mode = "live" if states == {"live"} else "mock" if states == {"mock"} else "mixed"
    return {"status": "ok", "mode": mode, "integrations": integrations, "version": VERSION}
