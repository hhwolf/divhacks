from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "upload_furniture_assets.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("upload_furniture_assets", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_discovers_all_bundled_furniture_assets() -> None:
    mod = _load_script()
    assets = mod.discover_assets()
    glbs = [a for a in assets if a.asset_kind == "glb"]
    thumbnails = [a for a in assets if a.asset_kind == "thumbnail"]
    manifests = [a for a in assets if a.asset_kind == "manifest"]
    assert len(glbs) == 26
    assert len(thumbnails) == 26
    assert len(manifests) == 1
    assert {a.furniture_id for a in glbs} == {a.furniture_id for a in thumbnails}
    assert all(a.local_path.exists() and a.byte_size > 0 for a in assets)
    assert next(a for a in glbs if a.furniture_id == "desk").storage_path == "glb/desk.glb"
    assert next(a for a in thumbnails if a.furniture_id == "desk").storage_path == "thumbs/desk.png"
