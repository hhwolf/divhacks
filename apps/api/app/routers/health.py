import importlib.util

from fastapi import APIRouter, Depends

from app.config import VERSION
from app.deps import AppContext, get_ctx

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness + which integrations are live (DigitalOcean health check)")
async def health(ctx: AppContext = Depends(get_ctx)) -> dict:
    s = ctx.settings
    integrations = {
        "gemini": "live" if s.gemini_live else "mock",
        "backboard": "live" if s.backboard_live else "mock",
        "mongo": s.store_kind,
        "blob": "live" if s.blob_live else "local",
        "usdz": "ready" if importlib.util.find_spec("pxr") else "unavailable",
    }
    ai = {integrations["gemini"], integrations["backboard"]}
    mode = "live" if ai == {"live"} else "mock" if ai == {"mock"} else "mixed"
    return {"status": "ok", "mode": mode, "integrations": integrations, "version": VERSION}
