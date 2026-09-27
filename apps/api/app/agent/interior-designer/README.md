# interior-designer

A Claude skill for the Adaptive Room Planner (DivHacks 2026). It acts as a senior interior designer who reads the room's 3D data, checks what fits using the app's own rules, and recommends up to 3 furniture arrangements in plain language.

```
SKILL.md                          persona, plain-language rules, 5-step workflow
scripts/validate_layout.py        PRD section 8 fit rules on a 10 cm grid (no dependencies)
scripts/inspect_glb.py            measures .glb/.gltf models: size, origin, rotation and unit bugs
scripts/roomplan_to_room.py       converts a raw RoomPlan export into the room format
references/room-data.md           coordinates, data model, how to read scans and models
references/space-planning.md      measurements in meters and feet
references/accessible-design.md   wheelchair, low-vision, aging-in-place numbers
references/style-and-color.md     styles, color and material rules
references/options-output.md      JSON for up to 3 variants, compatible with the PRD plan JSON
assets/sample_room.json           3.0 x 3.6 m demo bedroom with 3 test options
```

Try it: `python scripts/validate_layout.py assets/sample_room.json`
