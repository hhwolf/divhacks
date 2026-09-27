"""packages/contracts/rules.json is the one source for validation constants: the API loads and serves it, packages/geometry imports it."""

import json

from app.solver import constants
from fastapi.testclient import TestClient

from tests.conftest import ROOT

RULES = json.loads((ROOT / "packages" / "contracts" / "rules.json").read_text())


def test_rules_endpoint_serves_rules_json(client: TestClient) -> None:
    body = client.get("/validation/rules").json()
    assert body == RULES
    assert body["GRID_M"] == 0.1 and body["DOOR_CLEAR_M"] == 0.9 and body["ACCESS_EDGE_M"] == 0.75 and body["STORAGE_FRONT_M"] == 0.75
    assert body["DEFAULT_YOGA_ZONE_M"] == [1.8, 1.2]
    assert {r["id"] for r in body["rules"] if r["blocksSave"]} == {"bounds", "overlap"}
    assert {r["id"]: r["severity"] for r in body["rules"]}["walkable_path"] == "warning"


def test_python_constants_come_from_rules_json() -> None:
    assert constants.RULES_PATH == ROOT / "packages" / "contracts" / "rules.json"
    assert (constants.GRID, constants.DOOR_CLEARANCE, constants.ACCESS_EDGE, constants.STORAGE_FRONT) == (RULES["GRID_M"], RULES["DOOR_CLEAR_M"], RULES["ACCESS_EDGE_M"], RULES["STORAGE_FRONT_M"])
    assert constants.DEFAULT_YOGA_ZONE == tuple(RULES["DEFAULT_YOGA_ZONE_M"])


def test_typescript_reads_the_same_file() -> None:
    ts = (ROOT / "packages" / "geometry" / "src" / "constants.ts").read_text()
    assert "import rules from '@arp/contracts/rules.json'" in ts
    assert not [line for line in ts.splitlines() if line.startswith("export const") and "rules." not in line and "EPS" not in line and "M2_TO_SQFT" not in line]
