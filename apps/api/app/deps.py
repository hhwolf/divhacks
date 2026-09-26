"""Per-app wiring: settings, repository and integration adapters live on `app.state.ctx`."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Request

from app.config import Settings
from app.integrations.backboard import BackboardAdapter
from app.integrations.gemini import GeminiAdapter
from app.integrations.photon import PhotonAdapter
from app.models import User
from app.repo import make_repository
from app.repo.base import Repository


@dataclass
class AppContext:
    settings: Settings
    repo: Repository
    gemini: GeminiAdapter
    backboard: BackboardAdapter
    photon: PhotonAdapter

    @classmethod
    def build(cls, settings: Settings) -> AppContext:
        repo = make_repository(settings)
        return cls(settings, repo, GeminiAdapter(settings), BackboardAdapter(settings, repo), PhotonAdapter(settings))

    async def user_by_phone(self, phone: str) -> User:
        """The shared demo identity: one user per phone number, created on first contact."""
        found = await self.repo.list("users", phone=phone)
        if found:
            return User.model_validate(found[0])
        user = User(id=uuid.uuid4().hex[:12], phone=phone, createdAt=datetime.now(UTC).isoformat())
        await self.repo.insert("users", user.model_dump())
        return user

    async def demo_user(self) -> User:
        return await self.user_by_phone(self.settings.demo_phone)


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx
