"""The interior-designer skill, loaded verbatim from app/agent/interior-designer/ (a byte-for-byte copy of the Claude skill).

Gemini gets SKILL.md and the references the skill says to read, unchanged. The skill's own scripts
(validate_layout.py, inspect_glb.py) run server-side, because Gemini can't run them. Nothing in the
copied folder is edited: `interior-designer.lock.json` pins every file's sha256 and the tests and
scripts/check_designer.py fail if the copy drifts.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from functools import cache
from pathlib import Path
from types import ModuleType

SKILL_DIR = Path(__file__).resolve().parent / "interior-designer"
LOCK_PATH = Path(__file__).resolve().parent / "interior-designer.lock.json"

# SKILL.md step 3 and "Style and color" name these as read-when-needed; the other three are read on every request.
ALWAYS_READ = ("references/room-data.md", "references/space-planning.md", "references/options-output.md")
ACCESSIBLE_REF = "references/accessible-design.md"
STYLE_REF = "references/style-and-color.md"
_ACCESSIBLE_RE = re.compile(r"\b(wheelchair|cane|walker|crutch|blind|low[- ]vision|vision loss|mobility|accessib\w*|aging in place|elderly|disab\w*)\b", re.IGNORECASE)
_STYLE_RE = re.compile(r"\b(style|styled|restyle|colou?rs?|paint|palette|vibe|aesthetic|decor|japandi|boho|scandi\w*|minimalis\w*|mid-century|cozy|cosy|materials?|finish)\b", re.IGNORECASE)


def read(rel: str) -> str:
    return (SKILL_DIR / rel).read_text(encoding="utf-8")


def file_hashes(root: Path = SKILL_DIR) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def lock() -> dict[str, object]:
    return json.loads(LOCK_PATH.read_text())


def drift(root: Path = SKILL_DIR) -> list[str]:
    """Files that differ from the lock (changed, missing or extra). Empty means the copy is exact."""
    want: dict[str, str] = lock()["files"]  # type: ignore[assignment]
    have = file_hashes(root)
    return sorted({k for k in want.keys() | have.keys() if want.get(k) != have.get(k)})


def references_for(*texts: str | None) -> list[str]:
    """Which references SKILL.md asks for, given the request, remembered preferences and room purpose."""
    blob = " ".join(t for t in texts if t)
    refs = list(ALWAYS_READ)
    if _ACCESSIBLE_RE.search(blob):
        refs.append(ACCESSIBLE_REF)
    if _STYLE_RE.search(blob):
        refs.append(STYLE_REF)
    return refs


def instructions(*texts: str | None) -> str:
    """SKILL.md plus the references it calls for, each wrapped in a tag naming its file. Contents are not altered."""
    parts = [f'<skill name="interior-designer" file="SKILL.md">\n{read("SKILL.md")}\n</skill>']
    parts += [f'<skill-file path="{rel}">\n{read(rel)}\n</skill-file>' for rel in references_for(*texts)]
    return "\n\n".join(parts)


@cache
def script(name: str) -> ModuleType:
    """Import one of the skill's scripts (e.g. 'validate_layout') as a module without copying or editing it."""
    path = SKILL_DIR / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"interior_designer_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
