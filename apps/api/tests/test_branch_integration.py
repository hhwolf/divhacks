"""Ownership and deletion boundaries shared by furnishing and the housing/payment MVP."""
import asyncio
import io
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.dates import nyc_today
from app.furnish import MAX_PHOTO_BYTES


OWNER = {"X-Demo-Session": "branch-owner-" + "a" * 32}
OTHER = {"X-Demo-Session": "branch-other-" + "b" * 32}


def image_bytes(fmt="PNG"):
    output = io.BytesIO()
    Image.new("RGB", (12, 10), "tan").save(output, format=fmt)
    return output.getvalue()


def room(client, headers=OWNER):
    response = client.post("/rooms", headers=headers, json={"sample": "nyc-bedroom"})
    assert response.status_code == 201, response.text
    return response.json()


def evidence(client, room_id):
    response = client.post(f"/rooms/{room_id}/evidence", headers=OWNER, files={"image": ("leak.png", image_bytes(), "image/png")})
    assert response.status_code == 201, response.text
    return response.json()["photo"]


def test_cross_user_room_mutations_and_furnishing_are_denied(client, monkeypatch):
    from app.routers import rooms

    owner_room = room(client)
    other_room = room(client, OTHER)
    rid = owner_room["room"]["id"]
    runner = AsyncMock(side_effect=AssertionError("An unauthorized request reached furnishing"))
    monkeypatch.setattr(rooms, "furnish_room", runner)

    assert client.patch(f"/rooms/{rid}", headers=OTHER, json={"name": "Stolen room"}).status_code == 404
    assert client.delete(f"/rooms/{rid}", headers=OTHER).status_code == 404
    assert client.post(f"/rooms/{rid}/furnish", headers=OTHER, json={"theme": "minimal"}).status_code == 404
    assert client.post(f"/rooms/{rid}/furnish/photos", headers=OTHER, files={"images": ("inspiration.png", image_bytes(), "image/png")}).status_code == 404
    # An owned room cannot be used to pass another user's base layout through the new route.
    assert client.post(f"/rooms/{other_room['room']['id']}/furnish", headers=OTHER,
                       json={"theme": "minimal", "baseLayoutId": owner_room["currentLayout"]["id"]}).status_code == 404
    runner.assert_not_awaited()
    assert client.get(f"/rooms/{rid}", headers=OWNER).json()["room"]["name"] == owner_room["room"]["name"]
    renamed = client.patch(f"/rooms/{rid}", headers=OWNER, json={"name": "My renamed room"})
    assert renamed.status_code == 200 and renamed.json()["room"]["name"] == "My renamed room"


@pytest.mark.parametrize("kind,expected", [
    ("too_large", 413),
    ("unsupported_type", 422),
    ("disguised_bmp", 422),
    ("mismatched_mime", 422),
    ("not_an_image", 422),
])
def test_inspiration_upload_validation_precedes_furnishing(client, monkeypatch, kind, expected):
    from app.routers import rooms

    rid = room(client)["room"]["id"]
    runner = AsyncMock(side_effect=AssertionError("An invalid upload reached furnishing"))
    monkeypatch.setattr(rooms, "furnish_room", runner)
    payload, mime = image_bytes(), "image/png"
    if kind == "too_large":
        payload = b"x" * (MAX_PHOTO_BYTES + 1)
    elif kind == "unsupported_type":
        mime = "image/svg+xml"
    elif kind == "disguised_bmp":
        payload, mime = image_bytes("BMP"), "image/jpeg"
    elif kind == "mismatched_mime":
        mime = "image/jpeg"
    else:
        payload = b"<html>This is not a photo</html>"
    response = client.post(f"/rooms/{rid}/furnish/photos", headers=OWNER,
                           files={"images": ("inspiration.jpg", payload, mime)})
    assert response.status_code == expected, response.text
    runner.assert_not_awaited()


def test_room_delete_erases_private_evidence_and_housing_but_retains_receipt(client, data_dir):
    created = room(client)
    rid, lid = created["room"]["id"], created["currentLayout"]["id"]
    kept = room(client)
    photo = evidence(client, rid)
    kept_photo = evidence(client, kept["room"]["id"])
    profile = {
        "roomId": rid, "askingRent": 1600, "occupancyType": "private_room", "scanCoverage": "room",
        "measurementConfirmed": True, "dataMode": "demo",
        "conditions": [{"category": "leaks", "status": "ongoing", "severity": "moderate", "scope": "unit",
                        "source": "photo", "observedAt": nyc_today().isoformat(), "photoIds": [photo["id"]]}],
    }
    assert client.put(f"/rooms/{rid}/housing-profile", headers=OWNER, json=profile).status_code == 200
    assessment_response = client.post("/rent/assess", headers=OWNER, json=profile)
    assert assessment_response.status_code == 201, assessment_response.text
    assessment = assessment_response.json()["assessment"]
    agent_response = client.post("/agent/request", headers=OWNER,
                                 json={"roomId": rid, "baseLayoutId": lid, "text": "What is the weather?", "channel": "app"})
    assert agent_response.status_code == 200, agent_response.text
    request_id = agent_response.json()["requestId"]

    tenancy_response = client.post("/payments/test-tenancy", headers=OWNER, json={"roomId": rid})
    assert tenancy_response.status_code == 201, tenancy_response.text
    tenancy = tenancy_response.json()["tenancy"]
    quote_response = client.post("/payments/quote", headers=OWNER,
                                 json={"tenancyId": tenancy["id"], "amountCents": 50000, "purpose": "deposit", "rentalPeriod": "2026-09"})
    assert quote_response.status_code == 201, quote_response.text
    quote = quote_response.json()["quote"]
    checkout = client.post("/payments/checkout", headers=OWNER, json={"quoteId": quote["id"], "confirmed": True})
    assert checkout.status_code == 200, checkout.text
    payment_id = checkout.json()["payment"]["id"]
    receipt_response = client.post(f"/payments/{payment_id}/simulate", headers=OWNER, json={"outcome": "succeeded"})
    assert receipt_response.status_code == 200, receipt_response.text
    receipt = receipt_response.json()["payment"]

    repo = client.app.state.ctx.repo
    photo_doc = asyncio.run(repo.get("evidence", photo["id"]))
    path = data_dir / "private-evidence" / photo_doc["storageKey"]
    assert path.is_file()
    response = client.delete(f"/rooms/{rid}", headers=OWNER)
    assert response.status_code == 204, response.text
    assert not path.exists()
    for collection, doc_id in (("rooms", rid), ("layouts", lid), ("evidence", photo["id"]),
                               ("housing_profiles", rid), ("rent_assessments", assessment["id"]), ("agent_requests", request_id)):
        assert asyncio.run(repo.get(collection, doc_id)) is None, collection
    assert client.get(f"/evidence/{photo['id']}", headers=OWNER).status_code == 404
    assert client.get(f"/rooms/{rid}", headers=OWNER).status_code == 404
    assert client.get(f"/rooms/{kept['room']['id']}", headers=OWNER).status_code == 200
    assert client.get(f"/evidence/{kept_photo['id']}", headers=OWNER).status_code == 200
    assert client.get(f"/payments/{payment_id}", headers=OWNER).json()["payment"] == receipt
    assert receipt in client.get("/payments", headers=OWNER).json()["payments"]
    assert client.get(f"/payments/{payment_id}", headers=OTHER).status_code == 404


def test_failed_photo_erasure_keeps_ownership_records_for_retry(client, monkeypatch, data_dir):
    from fastapi import HTTPException
    from app.routers import evidence as evidence_router

    created = room(client)
    rid = created["room"]["id"]
    photo = evidence(client, rid)
    original_storage = evidence_router.storage

    async def fail_delete(ctx, method, key, data=None):
        if method == "DELETE":
            raise HTTPException(503, "Private photo storage unavailable")
        return await original_storage(ctx, method, key, data)

    monkeypatch.setattr(evidence_router, "storage", fail_delete)
    response = client.delete(f"/rooms/{rid}", headers=OWNER)
    assert response.status_code == 503
    assert client.get(f"/rooms/{rid}", headers=OWNER).status_code == 200
    assert client.get(f"/evidence/{photo['id']}", headers=OWNER).status_code == 200
    assert list((data_dir / "private-evidence").rglob("*.jpg"))
