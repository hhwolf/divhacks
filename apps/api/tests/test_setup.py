"""Room setup: space types → suggested elements, clean (unseeded) rooms, setup patch never touches the skeleton."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]


def test_space_types_and_suggestions(client: TestClient) -> None:
    types = client.get("/setup/space-types").json()
    assert {t["id"] for t in types} == {"bedroom", "study", "living", "workout", "creative", "shared"}
    r = client.get("/setup/suggestions", params={"types": "bedroom,workout,unknown"}).json()
    ids = [e["id"] for e in r["suggested"]]
    assert ids[:2] == ["bed", "nightstand"] and "yoga" in ids and len(ids) == len(set(ids))
    yoga = next(e for e in r["all"] if e["id"] == "yoga")
    assert yoga["zone"] == {"w": 1.8, "d": 1.2} and yoga["furnitureIds"] == ["yoga_mat"]


def test_clean_room_keeps_detected_objects_aside(client: TestClient) -> None:
    export = json.loads((ROOT / "fixtures/rooms/roomplan-export-sample.json").read_text())
    body = {"name": "Scanned", "skeleton": export["skeleton"], "objects": export["objects"], "seed": False,
            "spaceTypes": ["bedroom", "study"], "elements": [{"id": "bed", "label": "Bed", "furnitureIds": ["bed_double"]}, {"id": "custom-easel", "label": "Easel", "custom": True}]}
    r = client.post("/rooms", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["currentLayout"]["items"] == []
    assert len(data["room"]["detectedObjects"]) == len(export["objects"])
    assert data["room"]["spaceTypes"] == ["bedroom", "study"]
    assert [e["id"] for e in data["room"]["elements"]] == ["bed", "custom-easel"]
    assert data["room"]["skeleton"]["doors"] == export["skeleton"]["doors"]


def test_setup_patch_leaves_skeleton_untouched(client: TestClient) -> None:
    created = client.post("/rooms", json={"sample": "nyc-bedroom"}).json()
    rid = created["room"]["id"]
    r = client.patch(f"/rooms/{rid}/setup", json={"spaceTypes": ["living"], "elements": [{"id": "sofa", "label": "Sofa", "furnitureIds": ["sofa"]}]})
    assert r.status_code == 200
    room = client.get(f"/rooms/{rid}").json()["room"]
    assert room["spaceTypes"] == ["living"] and room["elements"][0]["id"] == "sofa"
    assert room["skeleton"] == created["room"]["skeleton"]
    assert client.patch("/rooms/nope/setup", json={"spaceTypes": []}).status_code == 404
