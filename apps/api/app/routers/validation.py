from fastapi import APIRouter

from app.solver.constants import RULES

router = APIRouter(prefix="/validation", tags=["validation"])


@router.get("/rules", summary="Shared validation constants (rules.json), read by the browser validator")
async def rules() -> dict:
    return RULES
