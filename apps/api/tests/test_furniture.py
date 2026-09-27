from pathlib import Path

from app.imports import parse_dims, parse_listing
from fastapi.testclient import TestClient

from tests.conftest import FIXTURES


def test_presets_listed_and_filtered(client: TestClient) -> None:
    items = client.get("/furniture").json()["items"]
    ids = {i["id"] for i in items}
    assert {"bed_double", "bed_single", "desk", "chair", "dresser", "nightstand", "bookshelf", "rug", "yoga_mat"} <= ids
    assert next(i for i in items if i["id"] == "desk")["dims"] == {"w": 1.2, "d": 0.6, "h": 0.75}
    beds = client.get("/furniture", params={"category": "bed"}).json()["items"]
    assert {i["id"] for i in beds} == {"bed_double", "bed_single"}
    assert {i["kind"] for i in client.get("/furniture", params={"category": "dresser"}).json()["items"]} == {"dresser"}


def test_seeded_presets_override_the_manifest(client: TestClient) -> None:
    """seed_presets.py writes preset docs (ownerless, Blob GLB URLs) into Mongo; they replace the bundled entry, never duplicate it."""
    import asyncio

    doc = {**next(i for i in client.get("/furniture").json()["items"] if i["id"] == "desk"), "glbUrl": "https://x.public.blob.vercel-storage.com/presets/desk.glb"}
    asyncio.run(client.app.state.ctx.repo.insert("furniture", doc))
    desks = [i for i in client.get("/furniture").json()["items"] if i["id"] == "desk"]
    assert len(desks) == 1 and desks[0]["glbUrl"].endswith("/presets/desk.glb")


def test_parse_listing_extracts_dims_and_price() -> None:
    meta = parse_listing((FIXTURES / "listings" / "desk.html").read_text())
    assert meta["price"] == 80.0
    assert meta["dims"] == {"w": 1.194, "d": 0.61, "h": 0.762}
    assert meta["jsonld"]["name"] == "Solid wood desk" and meta["og:title"].startswith("Solid wood desk")
    assert parse_dims('47" W x 24" D x 30" H') == {"w": 1.194, "d": 0.61, "h": 0.762}
    assert parse_dims("120 x 60 x 75 cm") == {"w": 1.2, "d": 0.6, "h": 0.75}
    assert parse_dims("no dimensions here") is None


def test_from_link_fixture(client: TestClient) -> None:
    r = client.post("/furniture/from-link", json={"url": "http://testserver/fixtures/listings/desk"})
    assert r.status_code == 201
    item = r.json()
    assert item["source"] == "link" and item["category"] == "imported" and item["kind"] == "desk"
    assert item["dims"] == {"w": 1.2, "d": 0.6, "h": 0.75} and item["price"] == 80 and item["estimated"] is False
    assert item["glbUrl"] == "/assets/furniture/desk.glb"
    assert any(i["id"] == item["id"] for i in client.get("/furniture").json()["items"])


def test_from_link_blocked_asks_for_screenshot(client: TestClient) -> None:
    r = client.post("/furniture/from-link", json={"url": "http://127.0.0.1:9/nothing"})
    assert r.status_code == 422
    assert "Upload a screenshot or enter the dimensions" in r.json()["detail"]["message"]


def test_from_photo_uploads_to_blob(client: TestClient, data_dir: Path) -> None:
    with (FIXTURES / "listings" / "desk.jpg").open("rb") as fh:
        r = client.post("/furniture/from-photo", files={"image": ("desk.jpg", fh, "image/jpeg")})
    assert r.status_code == 201
    item = r.json()
    assert item["source"] == "photo" and item["estimated"] is True and item["kind"] == "seating" and item["dims"]["h"] == 0.9
    assert item["photoUrl"].startswith("/blob/photos/") and item["photoUrl"].endswith(".jpg")
    assert (data_dir / "blob" / item["photoUrl"].removeprefix("/blob/")).read_bytes() == (FIXTURES / "listings" / "desk.jpg").read_bytes()
    assert client.get(item["photoUrl"]).status_code == 200


def test_manual(client: TestClient) -> None:
    for path in ("/furniture", "/furniture/manual"):
        r = client.post(path, json={"name": "IKEA Malm dresser", "dims": {"w": 0.8, "d": 0.48, "h": 1.0}, "price": 40})
        assert r.status_code == 201
        item = r.json()
        assert item["source"] == "manual" and item["kind"] == "dresser" and item["price"] == 40 and item["glbUrl"] == "/assets/furniture/dresser.glb"
