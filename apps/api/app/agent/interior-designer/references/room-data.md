# Reading the room data

The designer never "looks at" the 3D scene the way a person does. It reads the same numbers the editor draws from, which is more exact than eyeballing a render. This file explains those numbers.

## Coordinates (shared with the editor)

- Meters. The floor is the x/z plane, y is up (glTF and three.js convention)
- An item's `x`, `z` is the center of its footprint
- `rotation` is degrees around the vertical axis, same as three.js `rotation.y`. The PRD snaps to 0, 90, 180, 270
- At rotation 0, an item's width `w` runs along +x, its depth `d` along +z, and its front (the side you use: drawer fronts, the side you sit at, the foot of a bed) faces +z
- At rotation 90 the width runs along -z and the front faces +x. At 180 the front faces -z. At 270 the front faces -x
- The footprint on the floor at rotation 90 or 270 is d wide along x and w deep along z

If your team's editor uses a different origin (corner instead of center) or a different front direction, change the notes above and `Box.from_item` in `scripts/validate_layout.py` together.

## The room skeleton (`rooms` collection)

```json
{
  "floor_polygon": [[0, 0], [3.0, 0], [3.0, 3.6], [0, 3.6]],
  "doors":   [{"id": "door1",   "a": [2.1, 3.6], "b": [2.9, 3.6]}],
  "windows": [{"id": "window1", "a": [0.9, 0],   "b": [2.1, 0]}],
  "outlets": [{"id": "outlet1", "a": [0, 1.0],   "b": [0, 1.1]}]
}
```

Doors, windows and outlets are segments along a wall from point `a` to point `b`. Before designing, turn this into a picture in your head and say it back in one plain sentence, like: "It's a 3 by 3.6 m room (about 10 by 12 ft), window in the middle of the top wall, door in the bottom right corner." That sentence catches misreadings early.

Name walls by what's on them ("the window wall", "the door wall", "the wall your bed is on"), not by compass direction, unless the user uses compass directions.

## Raw RoomPlan scans

If you get Apple RoomPlan's own export (walls, doors, windows and objects each with `dimensions` and a 4x4 `transform`), run:

```
python scripts/roomplan_to_room.py scan.json > room.json
```

It builds the floor polygon from the walls, turns doors and windows into segments, and turns furniture RoomPlan detected into a draft Current Room. Read its `notes` for gaps between walls. RoomPlan's furniture sizes are estimates, so treat them as `estimated: true`.

## Furniture (`furniture` collection)

```json
{"name": "Marketplace desk", "category": "desk", "w": 1.2, "d": 0.6, "h": 0.75,
 "glb": "assets/desk_basic.glb", "source": "link", "price_usd": 80, "estimated": false}
```

Also accepted: `w_m`, `d_m`, `h_m` (the PRD plan format). `estimated: true` means the size came from a photo guess, so tell the user to measure before buying.

## 3D assets (.glb)

The catalog numbers and the 3D model can disagree. When you have the model file, measure it:

```
python scripts/inspect_glb.py assets/desk_basic.glb --expect 1.2 0.6 0.75
```

It reports the model's true width, depth and height, where its origin sits, and flags three common problems: the model is turned 90 degrees, it was built in centimeters, or its origin is at the center instead of the floor (it will sink into the floor). Report these to the builder in plain words; they're asset bugs, not design problems. For placement, trust the catalog `w`, `d` unless the user says the model is right.

## Layouts (`layouts` collection)

```json
{"name": "Current Room", "isCurrent": true,
 "items": [{"furnitureId": "bed", "x": 1.0, "z": 2.3, "rotation": 90, "locked": true}]}
```

`locked: true` means never move it. Backboard memory can add more non-negotiables ("never move my bed", "desk near natural light"); treat those the same as locks.

## Photos and screenshots

Use images for what the numbers can't tell you: style, color, clutter, how the light looks, what the user already owns. Don't measure distances from an isometric render; perspective and the tile grid make it easy to be off by 20 to 30 cm. The JSON is the source of truth for sizes and positions.
