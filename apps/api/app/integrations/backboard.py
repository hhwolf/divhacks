"""Backboard memory adapter.

Facts from https://docs.backboard.io and https://backboard-docs.docsalot.dev (fetched 2026-09-26):
- Base URL https://app.backboard.io/api, auth header `X-API-Key`.
- Memories are scoped to an assistant: POST /assistants/{assistant_id}/memories {content, metadata?} -> 201,
  GET /assistants/{assistant_id}/memories?page&page_size -> {memories[{id, content, metadata, score?, created_at}], total_count},
  POST /assistants/{assistant_id}/memories/search {query, limit} -> {memories[], total_count}.
- The `backboard-sdk` package wraps these with async `BackboardClient(api_key, base_url).add_memory / get_memories / search_memories`
  and `create_assistant(name=...)`; we create one assistant per demo user lazily and keep its id on the user document.
Mock mode keeps memories on the `users` document (`memories`), which the configured repository persists.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.repo.base import Repository

log = logging.getLogger(__name__)


class BackboardAdapter:
    def __init__(self, settings: Settings, repo: Repository) -> None:
        self.live = settings.backboard_live
        self._repo = repo
        self._client: Any = None
        if self.live:
            from backboard import BackboardClient

            self._client = BackboardClient(api_key=settings.backboard_api_key, base_url=settings.backboard_base_url)

    async def _assistant_id(self, user_id: str) -> str:
        user = await self._repo.get("users", user_id) or {}
        if user.get("backboardAssistantId"):
            return str(user["backboardAssistantId"])
        assistant = await self._client.create_assistant(name=f"roomplanner-{user_id}", description="FitCheck user memory")
        await self._repo.update("users", user_id, {"backboardAssistantId": str(assistant.assistant_id)})
        return str(assistant.assistant_id)

    async def get_context(self, user_id: str) -> list[str]:
        user = await self._repo.get("users", user_id) or {}
        local: list[str] = list(user.get("memories", []))
        if not self.live:
            return local
        try:
            res = await self._client.get_memories(await self._assistant_id(user_id))
            return [m.content for m in res.memories]
        except Exception as exc:  # network/credential problems must never break the demo
            log.warning("backboard get_memories failed, using local memories: %s", exc)
            return local

    async def add_memories(self, user_id: str, memories: list[str]) -> None:
        user = await self._repo.get("users", user_id) or {}
        merged = list(user.get("memories", []))
        merged.extend(m for m in memories if m not in merged)
        await self._repo.update("users", user_id, {"memories": merged})
        if not self.live:
            return
        try:
            assistant_id = await self._assistant_id(user_id)
            for m in memories:
                await self._client.add_memory(assistant_id, m, metadata={"source": "adaptive-room-planner"})
        except Exception as exc:
            log.warning("backboard add_memory failed: %s", exc)
