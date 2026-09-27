"""The API's wire shapes validate against packages/contracts/schemas (the same schemas the web/mobile types mirror).

Also re-checks the fixtures that packages/contracts/test/schemas.test.ts covers, so contract drift is caught from the Python side too.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tests.conftest import FIXTURES, ROOT

SCHEMAS = {p.name: json.loads(p.read_text()) for p in (ROOT / "packages" / "contracts" / "schemas").glob("*.json")}
REGISTRY = Registry().with_resources([(s["$id"], Resource.from_contents(s)) for s in SCHEMAS.values()])


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(SCHEMAS[name], registry=REGISTRY)


def _check(name: str, doc: dict) -> None:
    errors = sorted(validator(name).iter_errors(doc), key=str)
    assert not errors, f"{name}: {errors[0].message} at {list(errors[0].absolute_path)}"


@pytest.mark.parametrize("path", sorted((FIXTURES / "rooms").glob("*.json")), ids=lambda p: p.stem)
def test_sample_rooms_match_skeleton_schema(path: Path) -> None:
    _check("skeleton.schema.json", json.loads(path.read_text())["skeleton"])


@pytest.mark.parametrize("path", sorted((FIXTURES / "plans").glob("*.json")), ids=lambda p: p.stem)
def test_mock_plans_match_plan_schema(path: Path) -> None:
    _check("plan.schema.json", json.loads(path.read_text()))


def test_api_responses_match_contracts(client: TestClient, bedroom: dict, tmp_path: Path) -> None:
    from tests.usdz_factory import build_usdz

    with build_usdz(tmp_path / "scan.usdz").open("rb") as fh:
        scanned = client.post("/rooms", files={"usdz": ("Room.usdz", fh, "model/vnd.usdz+zip")}).json()
    for body in (client.get(f"/rooms/{bedroom['roomId']}").json(), client.get(f"/rooms/{scanned['room']['id']}").json()):
        _check("room.schema.json", body["room"])
        for layout in body["layouts"]:
            _check("layout.schema.json", layout)
    for item in client.get("/furniture").json()["items"]:
        _check("furniture.schema.json", item)
    texts = ("Will this fit beside my window? http://testserver/fixtures/listings/desk", "make space for yoga", "Which layout is better for studying?", "hello?",
             "I pay $1600 in 10027, is that fair?", "can I send a $900 deposit?")
    for text in texts:
        out = client.post("/agent/request", json={"roomId": bedroom["roomId"], "layoutId": bedroom["currentId"], "text": text}).json()
        _check("plan.schema.json", out["plan"])
        if out["layout"]:
            _check("layout.schema.json", out["layout"])
