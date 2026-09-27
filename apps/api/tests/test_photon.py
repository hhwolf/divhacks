import hashlib
import hmac
import json
import time
import base64
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
    assert body["ok"] is True and body["layoutId"] is None
    assert "confirm" in body["reply"]
    item = next(i for i in reversed(client.get('/furniture').json()['items']) if i['source'] in ('photo', 'link'))
    confirmed = client.patch(f"/furniture/{item['id']}/details", json={"name":item['name'],"dims":item['dims'],"category":item['category'],"dimensionsConfirmed":True})
    assert confirmed.status_code == 200
    result = client.post('/agent/request',json={"text":"Will this fit beside my window without moving my bed?","roomId":bedroom['roomId'],"baseLayoutId":bedroom['currentId'],"furnitureId":item['id'],"channel":"app"}).json()
    assert result['layout'] and result['layout']['createdBy'] == 'agent'
    outbox = client.app.state.ctx.photon.outbox
    assert outbox[-1]["to"] == payload["message"]["from"]
    assert outbox[-1]["text"] == body["reply"]
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


def _relay_headers(raw: bytes, secret: str = "relay-secret") -> dict[str, str]:
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"v0:{ts}:".encode() + raw, hashlib.sha256).hexdigest()
    return {"content-type": "application/json", "x-arp-relay-timestamp": ts, "x-arp-relay-signature": f"v0={sig}"}


def _post_normalized(client: TestClient, payload: dict, secret: str = "relay-secret"):
    raw = json.dumps(payload).encode()
    return client.post("/webhooks/photon/normalized", content=raw, headers=_relay_headers(raw, secret))


def test_normalized_photon_imports_marketplace_link_for_review(monkeypatch: pytest.MonkeyPatch, data_dir: Path, bedroom: dict) -> None:
    monkeypatch.setenv("PHOTON_RELAY_SECRET", "relay-secret")
    async def blocked_fetch(url: str):
        raise RuntimeError("blocked")
    monkeypatch.setattr("app.imports.fetch_bytes", blocked_fetch)
    with TestClient(create_app(Settings.from_env())) as c:
        # Recreate the room after Settings picks up PHOTON_RELAY_SECRET.
        created = c.post("/rooms", json={"sample": "nyc-bedroom"}).json()
        payload = {"messageId": "msg-marketplace-1", "sender": "+15555550100", "text": "https://facebook.com/marketplace/item/123", "attachments": []}
        r = _post_normalized(c, payload)
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True and body["itemId"].startswith("imp_")
        assert body["layoutId"] == created["currentLayout"]["id"]
        assert f"reviewFurniture={body['itemId']}" in body["links"][0]
        assert f"generateFurniture={body['itemId']}" in body["links"][1]
        assert body["reviewLink"] == body["links"][0]
        assert body["generateLink"] == body["links"][1]
        assert body["links"][0] not in body["reply"] and body["links"][1] not in body["reply"]
        item = c.get("/furniture").json()["items"][-1]
        assert item["source"] == "link" and item["sourceUrl"] == payload["text"]
        assert item["dimensionsConfirmed"] is False and item["estimated"] is True


def test_normalized_photon_replay_returns_same_response(monkeypatch: pytest.MonkeyPatch, bedroom: dict) -> None:
    monkeypatch.setenv("PHOTON_RELAY_SECRET", "relay-secret")
    async def blocked_fetch(url: str):
        raise RuntimeError("blocked")
    monkeypatch.setattr("app.imports.fetch_bytes", blocked_fetch)
    with TestClient(create_app(Settings.from_env())) as c:
        c.post("/rooms", json={"sample": "nyc-bedroom"}).json()
        payload = {"messageId": "msg-replay-1", "sender": "+15555550100", "text": "https://facebook.com/marketplace/item/abc", "attachments": []}
        first = _post_normalized(c, payload).json()
        second = _post_normalized(c, payload).json()
        assert second == first
        imported = [i for i in c.get("/furniture").json()["items"] if i["source"] == "link" and i.get("sourceUrl") == payload["text"]]
        assert len(imported) == 1


def test_normalized_photon_imports_screenshot_for_review(monkeypatch: pytest.MonkeyPatch, bedroom: dict) -> None:
    monkeypatch.setenv("PHOTON_RELAY_SECRET", "relay-secret")
    with TestClient(create_app(Settings.from_env())) as c:
        created = c.post("/rooms", json={"sample": "nyc-bedroom"}).json()
        payload = {
            "messageId": "msg-photo-1",
            "sender": "+15555550100",
            "text": "Could this chair fit?",
            "attachments": [{"mimeType": "image/jpeg", "fileName": "chair.jpg", "dataBase64": base64.b64encode(b"jpg").decode()}],
        }
        body = _post_normalized(c, payload).json()
        assert body["layoutId"] == created["currentLayout"]["id"]
        assert "estimated item" in body["reply"]
        assert f"generateFurniture={body['itemId']}" in body["generateLink"]
        item = c.get("/furniture").json()["items"][-1]
        assert item["source"] == "photo" and item["dimensionsConfirmed"] is False


def test_normalized_photon_rejects_unsigned_or_bad_signature(monkeypatch: pytest.MonkeyPatch, bedroom: dict) -> None:
    monkeypatch.setenv("PHOTON_RELAY_SECRET", "relay-secret")
    with TestClient(create_app(Settings.from_env())) as c:
        raw = json.dumps({"messageId": "msg-bad", "sender": "+1555", "text": "", "attachments": []}).encode()
        assert c.post("/webhooks/photon/normalized", content=raw).status_code == 401
        assert c.post("/webhooks/photon/normalized", content=raw, headers=_relay_headers(raw, "wrong")).status_code == 401
