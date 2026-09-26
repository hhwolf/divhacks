from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.agent import pipeline
from app.agent.router import route
from app.deps import AppContext, get_ctx
from app.integrations.photon import Attachment
from app.models import Channel

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequestBody(BaseModel):
    text: str
    roomId: str
    baseLayoutId: str
    furnitureId: str | None = None
    imageUrl: str | None = None
    channel: Channel = "app"


@router.post("/request")
async def agent_request(body: AgentRequestBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    attachments = [Attachment(url=body.imageUrl, mime_type="image/jpeg")] if body.imageUrl else []
    routed = await route(ctx, user.id, body.text, attachments, body.furnitureId)
    out = await pipeline.run(
        ctx, request_text=routed.text, user_id=user.id, room_id=body.roomId, base_layout_id=body.baseLayoutId, furniture_id=routed.furniture_id, channel=body.channel
    )
    return {
        "plan": out.plan.model_dump(exclude_none=True) if out.plan else None,
        "layout": out.layout,
        "reply": out.reply,
        "status": out.status,
        "links": out.links,
        "requestId": out.request_id,
        "violations": [v.model_dump() for v in out.violations],
    }
