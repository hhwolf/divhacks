from app.imports import parse_dims, parse_listing
from fastapi.testclient import TestClient

from tests.conftest import FIXTURES


def test_presets_listed(client: TestClient) -> None:
    items = client.get("/furniture").json()["items"]
    ids = {i["id"] for i in items}
    assert {"bed_double", "desk", "dresser", "yoga_mat"} <= ids
    assert next(i for i in items if i["id"] == "desk")["dims"] == {"w": 1.2, "d": 0.6, "h": 0.75}


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


def test_from_link_unreachable_host(client: TestClient) -> None:
    assert client.post("/furniture/from-link", json={"url": "http://127.0.0.1:9/nothing"}).status_code == 502


def test_from_photo(client: TestClient) -> None:
    with (FIXTURES / "listings" / "desk.jpg").open("rb") as fh:
        r = client.post("/furniture/from-photo", files={"image": ("desk.jpg", fh, "image/jpeg")})
    assert r.status_code == 201
    item = r.json()
    assert item["source"] == "photo" and item["estimated"] is True and item["kind"] == "seating" and item["dims"]["h"] == 0.9


def test_manual(client: TestClient) -> None:
    r = client.post("/furniture/manual", json={"name": "IKEA Malm dresser", "dims": {"w": 0.8, "d": 0.48, "h": 1.0}, "price": 40})
    assert r.status_code == 201
    item = r.json()
    assert item["source"] == "manual" and item["kind"] == "dresser" and item["price"] == 40 and item["glbUrl"] == "/assets/furniture/dresser.glb"
