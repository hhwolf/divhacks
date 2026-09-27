"""Shared geometry constants from packages/contracts/rules.json: the file the TS validator imports and GET /validation/rules serves."""

import json
import math
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).resolve().parents[4] / "packages" / "contracts" / "rules.json"
RULES: dict[str, Any] = json.loads(RULES_PATH.read_text())

GRID: float = RULES["GRID_M"]  # m, validation grid
DOOR_CLEARANCE: float = RULES["DOOR_CLEAR_M"]  # m in front of a door
ACCESS_EDGE: float = RULES["ACCESS_EDGE_M"]  # m free band along one long edge of beds/desks
STORAGE_FRONT: float = RULES["STORAGE_FRONT_M"]  # m free band in front of wardrobes/dressers/storage
DEFAULT_YOGA_ZONE: tuple[float, float] = tuple(RULES["DEFAULT_YOGA_ZONE_M"])  # type: ignore[assignment]
ACCESS_FREE_RATIO: float = RULES["ACCESS_FREE_RATIO"]  # fraction of a band that must be free for the edge to count
WINDOW_BAND: float = RULES["WINDOW_BAND_M"]  # m depth of the window keep-clear band
CORRIDOR_CELLS: int = RULES["CORRIDOR_CELLS"]  # erosion radius (cells) for a "comfortable" 0.5 m path
EPS = 1e-6
M2_TO_SQFT = 10.7639


def js_round(v: float) -> int:
    """JavaScript Math.round (half toward +infinity), unlike Python's banker's rounding."""
    return int(math.floor(v + 0.5))
