"""Port of formatLength from packages/geometry/src/units.ts (imperial branch)."""

import math

from app.solver.constants import js_round

_IN = 0.0254


def format_length_imperial(m: float) -> str:
    """1.2192 -> 4' 0"; values under 3 ft print as inches: 0.457 -> 18 in."""
    inches = m / _IN
    if inches < 36:
        return f"{js_round(inches)} in"
    ft = math.floor(inches / 12)
    rem = js_round(inches - ft * 12)
    return f"{ft + 1}' 0\"" if rem == 12 else f"{ft}' {rem}\""
