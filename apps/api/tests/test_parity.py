"""TS/Python parity: every fixture in fixtures/validation must reproduce the TypeScript validator's output."""

import json
from pathlib import Path

import pytest
from app.models import FurnitureRef, LayoutItem, RoomSkeleton, Zone
from app.solver.validate import validate_layout

FIXTURES = sorted((Path(__file__).resolve().parents[3] / "fixtures" / "validation").glob("*.json"))


def _key(rule: str, items: list[str]) -> str:
    return f"{rule}:{','.join(sorted(items))}"


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_fixture_parity(path: Path) -> None:
    fx = json.loads(path.read_text())
    furniture = {k: FurnitureRef.model_validate(v) for k, v in fx["furniture"].items()}
    items = [LayoutItem.model_validate(i) for i in fx["layout"]["items"]]
    zones = [Zone.model_validate(z) for z in fx["layout"].get("zones", [])]
    base = [LayoutItem.model_validate(i) for i in fx["baseLayout"]["items"]] if fx.get("baseLayout") else None
    res = validate_layout(RoomSkeleton.model_validate(fx["skeleton"]), furniture, items, zones, base)
    exp = fx["expected"]

    assert sorted(_key(v.rule, v.items) for v in res.violations) == sorted(_key(v["rule"], v["items"]) for v in exp["violations"])
    assert {(_key(v.rule, v.items), v.message) for v in res.violations} == {(_key(v["rule"], v["items"]), v["message"]) for v in exp["violations"]}
    assert res.blocked == exp["blocked"]
    m, em = res.metrics, exp["metrics"]
    assert m.conflicts == em["conflicts"]
    assert m.walkability == em["walkability"]
    assert m.openFloor == pytest.approx(em["openFloor"], abs=0.11)
    assert m.reachableStorage == pytest.approx(em["reachableStorage"], abs=0.11)
    assert m.largestFreeRect is not None
    assert m.largestFreeRect.fits == em["largestFreeRect"]["fits"]
    assert m.largestFreeRect.areaM2 == pytest.approx(em["largestFreeRect"]["areaM2"], abs=0.011)
    fired = {v.rule for v in res.violations}
    for rule in fx["expectRules"]:
        assert rule in fired
