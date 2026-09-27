"""Verify bearer tokens with Supabase Auth; never trust a client-supplied user id."""
from dataclasses import dataclass
import hashlib
import re

import httpx
from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Principal:
    id: str
    authenticated: bool
    phone: str = ""


async def resolve_principal(request: Request) -> Principal:
    settings = request.app.state.ctx.settings
    auth = request.headers.get("authorization", "")
    if auth:
        if not auth.startswith("Bearer ") or not settings.supabase_url:
            raise HTTPException(401, "Sign in again")
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                res = await client.get(f"{settings.supabase_url}/auth/v1/user", headers={
                    "apikey": settings.supabase_publishable_key or settings.supabase_secret_key,
                    "authorization": auth,
                })
            if res.status_code != 200:
                raise HTTPException(401, "Session expired or invalid")
            user = res.json()
            if not user.get("id") or user.get("is_anonymous"):
                raise HTTPException(401, "A verified sign-in is required")
            phone = user.get("phone", "") if user.get("phone_confirmed_at") else ""
            return Principal(user["id"], True, phone)
        except httpx.HTTPError as exc:
            raise HTTPException(503, "Authentication service unavailable") from exc
    # An opaque per-browser demo secret isolates even synthetic rooms and demo photos.
    # Legacy CLI demos without a header share ONLY the synthetic demo namespace.
    token = request.headers.get("x-demo-session", "")
    if token and not re.fullmatch(r"[a-zA-Z0-9_-]{32,128}", token):
        raise HTTPException(400, "Invalid demo session")
    return Principal("demo_" + hashlib.sha256(token.encode()).hexdigest()[:32], False)
