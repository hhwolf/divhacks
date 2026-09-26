"""Photon (Spectrum) iMessage adapter: inbound normalization + signature check, outbound send.

Facts from https://photon.codes/docs/webhooks/* and https://spectrum.photon.codes/openapi/json (fetched 2026-09-26):
- Inbound webhook body: {"event": "messages", "space": {id, platform, type?, phone?}, "message": {id, platform, direction: "inbound",
  timestamp, sender: {id, platform}, space, content: {type: "text", text} | {type: "attachment", id, name, mimeType, size} | {type: "reaction", ...}}}.
  `message.id` is the idempotency key. Webhooks registered with schema "raw-inbound.v1" deliver the provider's raw body instead.
- Signature: headers `X-Spectrum-Timestamp` (unix seconds) and `X-Spectrum-Signature` = "v0=" + hex(HMAC-SHA256(secret, f"v0:{ts}:{raw_body}")).
  Reject timestamps older than 5 minutes; compare with hmac.compare_digest. Standard-Webhooks headers (`webhook-id`, `webhook-timestamp`,
  `webhook-signature` = "v1,<base64>", secret prefixed `whsec_`, signed content f"{id}.{ts}.{body}") are also delivered; both are accepted here.
- Outbound: Photon's REST API (spectrum.photon.codes) is a management plane only (webhooks, lines, users, tokens); runtime sending is
  documented exclusively through the `spectrum-ts` SDK. Live `send_text` therefore POSTs to `{PHOTON_BASE_URL}/messages` with a Bearer key,
  which is the shape a thin spectrum-ts relay would expose; there is no public REST send endpoint to target directly.
Our own fixtures (fixtures/photon/*.json) use the normalized shape in packages/contracts/schemas/photon-inbound.schema.json.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings

MAX_SKEW_S = 300


@dataclass
class Attachment:
    url: str | None
    mime_type: str | None


@dataclass
class InboundMessage:
    sender: str
    text: str
    message_id: str | None = None
    attachments: list[Attachment] = field(default_factory=list)


def _attachments(raw: Any) -> list[Attachment]:
    out: list[Attachment] = []
    for a in raw or []:
        if isinstance(a, dict):
            out.append(Attachment(url=a.get("url"), mime_type=a.get("mimeType") or a.get("mime_type")))
    return out


def normalize_inbound(body: Any) -> InboundMessage | None:
    """Map our fixture shape, the real Spectrum event shape, or any message/text/from-like body onto InboundMessage."""
    if not isinstance(body, dict):
        return None
    msg = body.get("message")
    if isinstance(msg, dict):
        sender = msg.get("from") or (msg.get("sender") or {}).get("id") or (body.get("space") or {}).get("phone") or (msg.get("space") or {}).get("phone")
        content = msg.get("content") if isinstance(msg.get("content"), dict) else {}
        text = msg.get("text") if isinstance(msg.get("text"), str) else content.get("text", "")
        attachments = _attachments(msg.get("attachments"))
        if content.get("type") == "attachment":
            attachments.append(Attachment(url=content.get("url"), mime_type=content.get("mimeType")))
        if sender:
            return InboundMessage(sender=str(sender), text=text or "", message_id=msg.get("id"), attachments=attachments)
    sender = body.get("from") or body.get("sender") or body.get("phone")
    text = body.get("text") or body.get("body") or (msg if isinstance(msg, str) else None)
    if sender and isinstance(text, str):
        return InboundMessage(sender=str(sender), text=text, message_id=body.get("id"), attachments=_attachments(body.get("attachments")))
    return None


def verify_signature(secret: str, raw_body: bytes, headers: Mapping[str, str]) -> bool:
    h = {k.lower(): v for k, v in headers.items()}
    if "x-spectrum-signature" in h and "x-spectrum-timestamp" in h:
        ts = h["x-spectrum-timestamp"]
        if not _fresh(ts):
            return False
        expected = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, h["x-spectrum-signature"])
    if "webhook-signature" in h and "webhook-timestamp" in h and "webhook-id" in h:
        ts = h["webhook-timestamp"]
        if not _fresh(ts):
            return False
        key = base64.b64decode(secret.split("whsec_", 1)[-1]) if secret.startswith("whsec_") else secret.encode()
        digest = base64.b64encode(hmac.new(key, f"{h['webhook-id']}.{ts}.".encode() + raw_body, hashlib.sha256).digest()).decode()
        return any(hmac.compare_digest(digest, sig.split(",", 1)[-1]) for sig in h["webhook-signature"].split())
    return False


def _fresh(ts: str) -> bool:
    try:
        return abs(time.time() - float(ts)) <= MAX_SKEW_S
    except ValueError:
        return False


class PhotonAdapter:
    def __init__(self, settings: Settings) -> None:
        self.live = settings.photon_live
        self.secret = settings.photon_webhook_secret
        self.sender = settings.photon_from
        self._base = settings.photon_base_url.rstrip("/")
        self._key = settings.photon_api_key
        self.outbox: list[dict[str, Any]] = []
        self._outbox_path: Path = settings.data_dir / "photon_outbox.jsonl"

    async def send_text(self, to: str, text: str, links: list[str]) -> dict[str, Any]:
        record: dict[str, Any] = {"to": to, "from": self.sender or None, "text": text, "links": links, "at": datetime.now(UTC).isoformat()}
        if not self.live:
            self.outbox.append(record)
            self._outbox_path.parent.mkdir(parents=True, exist_ok=True)
            with self._outbox_path.open("a") as fh:
                fh.write(json.dumps(record) + "\n")
            return {**record, "delivery": "mock"}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self._base}/messages",
                headers={"Authorization": f"Bearer {self._key}"},
                json={"to": to, "from": self.sender or None, "text": "\n".join([text, *links])},
            )
            resp.raise_for_status()
        return {**record, "delivery": "live", "status": resp.status_code}
