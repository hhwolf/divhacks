"""Room-setup vocabulary: space types and the elements each one usually needs (shared by the mobile setup flow and the web checklist)."""

from __future__ import annotations

from app.models import RoomElement

SPACE_TYPES: list[dict[str, str]] = [
    {"id": "bedroom", "label": "Bedroom", "icon": "bed"},
    {"id": "study", "label": "Study", "icon": "desk"},
    {"id": "living", "label": "Living room", "icon": "sofa"},
    {"id": "workout", "label": "Workout", "icon": "yoga"},
    {"id": "creative", "label": "Creative studio", "icon": "palette"},
    {"id": "shared", "label": "Shared room", "icon": "people"},
]

ELEMENTS: dict[str, RoomElement] = {
    e.id: e
    for e in [
        RoomElement(id="bed", label="Bed", furnitureIds=["bed_double", "bed_single"]),
        RoomElement(id="nightstand", label="Nightstand", furnitureIds=["nightstand"]),
        RoomElement(id="wardrobe", label="Wardrobe or dresser", furnitureIds=["wardrobe", "dresser"]),
        RoomElement(id="desk", label="Desk and chair", furnitureIds=["desk", "chair_desk"]),
        RoomElement(id="storage", label="Shelving / storage", furnitureIds=["bookshelf", "bookshelf_low"]),
        RoomElement(id="reading", label="Reading corner", furnitureIds=["armchair", "floor_lamp", "bookshelf_low"]),
        RoomElement(id="sofa", label="Sofa", furnitureIds=["sofa", "armchair"]),
        RoomElement(id="coffee_table", label="Coffee table", furnitureIds=["coffee_table", "side_table"]),
        RoomElement(id="tv", label="TV stand", furnitureIds=["tv_stand"]),
        RoomElement(id="dining", label="Small dining table", furnitureIds=["table_round", "table", "chair"]),
        RoomElement(id="yoga", label="Yoga / workout zone", furnitureIds=["yoga_mat"], zone={"w": 1.8, "d": 1.2}),
        RoomElement(id="worktable", label="Work table", furnitureIds=["table", "stool"]),
        RoomElement(id="plants", label="Plants", furnitureIds=["plant"]),
        RoomElement(id="rug", label="Rug", furnitureIds=["rug"]),
        RoomElement(id="second_bed", label="Second bed", furnitureIds=["bed_single"]),
        RoomElement(id="second_desk", label="Second desk", furnitureIds=["desk", "chair_desk"]),
        RoomElement(id="mini_fridge", label="Mini fridge", furnitureIds=["mini_fridge"]),
    ]
}

SUGGESTIONS: dict[str, list[str]] = {
    "bedroom": ["bed", "nightstand", "wardrobe", "storage", "rug"],
    "study": ["desk", "storage", "reading", "plants"],
    "living": ["sofa", "coffee_table", "tv", "rug", "plants"],
    "workout": ["yoga", "storage"],
    "creative": ["worktable", "storage", "plants", "desk"],
    "shared": ["second_bed", "second_desk", "wardrobe", "mini_fridge"],
}


def suggest_elements(space_types: list[str]) -> list[RoomElement]:
    """Union of suggestions in space-type order, de-duplicated, unknown types ignored."""
    out: list[RoomElement] = []
    seen: set[str] = set()
    for st in space_types:
        for key in SUGGESTIONS.get(st, []):
            if key not in seen:
                seen.add(key)
                out.append(ELEMENTS[key])
    return out
