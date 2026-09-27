"""Per-app wiring: settings, repository, file storage and integration adapters live on `app.state.ctx`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Request

from app.config import DEMO_USER_ID, DEMO_USER_NAME, Settings
from app.integrations.backboard import BackboardAdapter
from app.integrations.gemini import GeminiAdapter
from app.models import User
from app.repo import make_repository
from app.repo.base import Repository
from app.services.blob import BlobStorage, make_blob_storage


@dataclass
class AppContext:
    settings: Settings
    repo: Repository
    blob: BlobStorage
    gemini: GeminiAdapter
    backboard: BackboardAdapter

    @classmethod
    def build(cls, settings: Settings) -> AppContext:
        repo = make_repository(settings)
        return cls(settings, repo, make_blob_storage(settings), GeminiAdapter(settings), BackboardAdapter(settings, repo))

    async def demo_user(self) -> User:
        """The one shared demo user (no sign-in), created on first use."""
        found = await self.repo.get("users", DEMO_USER_ID)
        if found:
            return User.model_validate({"displayName": DEMO_USER_NAME, **found})
        user = User(id=DEMO_USER_ID, displayName=DEMO_USER_NAME, createdAt=datetime.now(UTC).isoformat())
        await self.repo.insert("users", user.model_dump())
        return user


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx
