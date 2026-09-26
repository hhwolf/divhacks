"""Shared geometry constants. Mirrors packages/geometry/src/constants.ts exactly."""

GRID = 0.1  # m, validation grid
EPS = 1e-6
DOOR_CLEARANCE = 0.9  # m in front of a door
ACCESS_EDGE = 0.75  # m free band for beds/desks/wardrobes/dressers
ACCESS_FREE_RATIO = 0.7  # fraction of the band that must be free for the edge to count
WINDOW_BAND = 0.6  # m depth of the window keep-clear band
CORRIDOR_CELLS = 2  # erosion radius (cells) for a "comfortable" 0.5 m path
M2_TO_SQFT = 10.7639


def js_round(v: float) -> int:
    """JavaScript Math.round (half toward +infinity), unlike Python's banker's rounding."""
    import math

    return int(math.floor(v + 0.5))
