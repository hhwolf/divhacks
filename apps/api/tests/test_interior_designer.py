"""The interior-designer merge check (scripts/check_designer.py) as tests, plus the pieces it relies on.

The live Gemini quiz is not run here; `make designer-check` runs it when GEMINI_API_KEY is set.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from app.agent import skill
from app.agent.pipeline import plan_options
from app.integrations.gemini import PLAN_SCHEMA, strip_schema
from app.models import AgentPlan

_spec = importlib.util.spec_from_file_location("check_designer", Path(__file__).resolve().parents[1] / "scripts" / "check_designer.py")
assert _spec and _spec.loader
check_designer = sys.modules["check_designer"] = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_designer)


@pytest.mark.parametrize("name,fn", [(n, fn) for _, n, fn in check_designer.CHECKS], ids=[n for _, n, _ in check_designer.CHECKS])
def test_merge_check(name: str, fn, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ARP_DATA_DIR", str(tmp_path))
    for var in ("GEMINI_API_KEY", "BACKBOARD_API_KEY", "SUPABASE_URL", "SUPABASE_SECRET_KEY", "BLOB_READ_WRITE_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    result = check_designer._check("", name, fn)
    if result.status == "SKIP":
        pytest.skip(result.detail)
    assert result.status == "PASS", result.detail


def test_copy_is_the_skill_unedited() -> None:
    assert skill.drift() == []
    assert skill.read("SKILL.md").startswith("---\nname: interior-designer\n")


def test_references_load_when_the_skill_says() -> None:
    assert skill.references_for("will this desk fit?") == list(skill.ALWAYS_READ)
    assert skill.ACCESSIBLE_REF in skill.references_for("", "my roommate uses a wheelchair")
    assert skill.STYLE_REF in skill.references_for("what colors would make it feel bigger?")


def test_options_become_single_plans_favorite_first() -> None:
    plan = AgentPlan.model_validate({
        "intent": "fit_item", "variantName": "Window Desk", "reply": "x", "recommended": "Window Desk",
        "constraints": [{"type": "lock", "item": "bed"}, {"type": "adjacent", "item": "desk", "feature": "window"}],
        "actions": [{"type": "add", "item": "desk", "zone": "window wall"}],
        "options": [
            {"variantName": "Desk by the Door", "actions": [{"type": "add", "item": "desk", "zone": "door wall"}]},
            {"variantName": "Window Desk", "actions": [{"type": "add", "item": "desk", "zone": "window wall"}]},
        ],
    })
    (fav, _), (other, _) = plan_options(plan)
    assert fav.variantName == "Window Desk" and {c.type for c in fav.constraints} == {"lock", "adjacent"}
    assert other.variantName == "Desk by the Door" and [c.type for c in other.constraints] == ["lock"]  # the favorite's adjacency isn't forced on it


def test_response_schema_has_no_refs_for_gemini() -> None:
    assert "$ref" not in str(strip_schema(PLAN_SCHEMA))
    assert strip_schema(PLAN_SCHEMA)["properties"]["options"]["items"]["properties"]["actions"]["items"]["required"] == ["type", "item"]
