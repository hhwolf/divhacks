import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest
from app.config import Settings
from app.integrations.photon import normalize_inbound, verify_signature
from app.main import create_app
from fastapi.testclient import TestClient

from tests.conftest import FIXTURES, load_fixture

PHOTON_FIXTURES = sorted(p.name for p in (FIXTURES / "photon").glob("*.json"))
PHOTON_FURNITURE_FIXTURES = [name for name in PHOTON_FIXTURES if name != "yoga.json"]


@pytest.mark.parametrize("name", PHOTON_FURNITURE_FIXTURES)
def test_fixture_round_trip_creates_variant(client: TestClient, bedroom: dict, name: str, data_dir: Path) -> None:
    payload = load_fixture("photon", name)
    r = client.post("/webhooks/photon", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["layoutId"]
    layouts = client.get(f"/rooms/{bedroom['roomId']}").json()["layouts"]
    assert any(l["id"] == body["layoutId"] and l["createdBy"] == "agent" for l in layouts)
    outbox = client.app.state.ctx.photon.outbox
    assert outbox[-1]["to"] == payload["message"]["from"]
    assert outbox[-1]["text"] == body["reply"]
    assert f"roomplanner://layout/{body['layoutId']}" in outbox[-1]["links"]
    lines = (data_dir / "photon_outbox.jsonl").read_text().splitlines()
    assert json.loads(lines[-1])["links"] == outbox[-1]["links"]


def test_photon_plain_spatial_request_redirects_to_app(client: TestClient, bedroom: dict) -> None:
    r = client.post("/webhooks/photon", json=load_fixture("photon", "yoga.json"))
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["layoutId"] is None
    assert "listing link or photo" in body["reply"]
    assert "in-app assistant" in body["reply"]
    assert [l["name"] for l in client.get(f"/rooms/{bedroom['roomId']}").json()["layouts"]] == ["Current Room"]


def test_unknown_shape_gets_clarifying_reply(client: TestClient) -> None:
    r = client.post("/webhooks/photon", json={"hello": "world"})
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["reply"].endswith("?")
    r = client.post("/webhooks/photon", content=b"not json", headers={"content-type": "application/json"})
    assert r.status_code == 200


def test_no_room_yet_replies_gracefully(client: TestClient) -> None:
    r = client.post("/webhooks/photon", json=load_fixture("photon", "text-question.json"))
    assert r.status_code == 200 and r.json()["layoutId"] is None and "room" in r.json()["reply"]


def test_normalize_real_spectrum_shape() -> None:
    body = {
        "event": "messages",
        "space": {"id": "any;-;+15550100", "platform": "iMessage", "type": "dm", "phone": "+15551234567"},
        "message": {"id": "spc-msg-1", "platform": "iMessage", "direction": "inbound", "timestamp": "2026-05-14T19:06:32.000Z",
                    "sender": {"id": "+15551234567", "platform": "iMessage"}, "content": {"type": "text", "text": "hey"}},
    }
    msg = normalize_inbound(body)
    assert msg and msg.sender == "+15551234567" and msg.text == "hey" and msg.message_id == "spc-msg-1"
    body["message"]["content"] = {"type": "attachment", "id": "x", "name": "IMG.HEIC", "mimeType": "image/heic", "size": 1}
    msg = normalize_inbound(body)
    assert msg and msg.attachments[0].mime_type == "image/heic"
    assert normalize_inbound({"from": "+1555", "text": "hi"}).text == "hi"


def test_signature_verification(monkeypatch: pytest.MonkeyPatch, data_dir: Path, bedroom: dict) -> None:
    monkeypatch.setenv("PHOTON_WEBHOOK_SECRET", "s3cret")
    with TestClient(create_app(Settings.from_env())) as c:
        raw = json.dumps(load_fixture("photon", "yoga.json")).encode()
        ts = str(int(time.time()))
        sig = "v0=" + hmac.new(b"s3cret", f"v0:{ts}:".encode() + raw, hashlib.sha256).hexdigest()
        assert c.post("/webhooks/photon", content=raw, headers={"X-Spectrum-Timestamp": ts, "X-Spectrum-Signature": "v0=bad"}).status_code == 401
        assert c.post("/webhooks/photon", content=raw).status_code == 401
        assert c.post("/webhooks/photon", content=raw, headers={"X-Spectrum-Timestamp": ts, "X-Spectrum-Signature": sig}).status_code == 200
    assert not verify_signature("s3cret", raw, {"X-Spectrum-Timestamp": str(int(time.time()) - 3600), "X-Spectrum-Signature": sig})
