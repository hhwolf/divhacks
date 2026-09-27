# Options output

Use this format whenever the request comes from the app, the backend, the Photon agent, or the user asks for JSON. It extends the PRD's plan JSON (section 7) from one placement to up to three options, so the backend can turn each one into a named layout variant.

Return the JSON object only, no markdown fences, when software is calling. When a person is chatting, give the plain-language answer first and the JSON after it only if they asked for it.

## Schema

```json
{
  "intent": "fit_item",
  "item": {"type": "desk", "w_m": 1.2, "d_m": 0.6, "h_m": 0.75, "price_usd": 80},
  "constraints": [
    {"type": "lock", "item": "bed"},
    {"type": "adjacent", "item": "desk_mkt", "feature": "window1"}
  ],
  "room_summary": "A 3 by 3.6 m bedroom (about 10 by 12 ft) with the window on the top wall and the door in the bottom right corner.",
  "options": [
    {
      "variantName": "Window Desk",
      "items": [
        {"furnitureId": "bed", "x": 1.0, "z": 2.3, "rotation": 90, "locked": true},
        {"furnitureId": "dresser", "x": 2.775, "z": 1.0, "rotation": 270, "locked": false},
        {"furnitureId": "desk_mkt", "x": 1.5, "z": 0.3, "rotation": 0, "locked": false}
      ],
      "moved": ["desk_mkt"],
      "explanation": "The desk sits right under the window, so you get daylight while you work, and your bed stays exactly where it is.",
      "tradeoff": "The desk corner is 5 cm in front of the dresser, so the bottom drawer will bump the desk leg.",
      "validation": {"ok": true, "warnings": 1, "open_floor_pct": 64.4}
    }
  ],
  "recommended": "Window Desk",
  "reply": "Yes, it fits under your window without touching your bed. I made a layout called Window Desk: <link>",
  "clarifying_question": null
}
```

## Field rules

- `options`: 1 to 3 entries. Each one is a complete layout (every item in the room, with locks), so the backend can save it as a variant as-is. Drop any option that fails validation. Never pad to three with near-duplicates
- `variantName`: 1 to 3 plain words a user would say out loud ("Window Desk", "Yoga Corner", "Desk by the Door"). No numbering like "Option 2"
- `moved`: ids of items that are new or changed position compared with the Current Room. Locked items must never appear here
- `explanation`: 1 to 2 sentences, plain language, says why this arrangement is good for this person
- `tradeoff`: 1 sentence, the honest downside. Every real option has one
- `validation`: copied from `scripts/validate_layout.py` output for that option (`ok`, number of warnings, `open_floor_pct`)
- `recommended`: the `variantName` you'd pick, first in the `options` list
- `reply`: one sentence for iMessage (Photon), plus the link placeholder. If nothing fits, say by how much and suggest one alternative: "It's 12 cm too wide for the window wall. It would fit on the wall by the door. Want me to try that?"
- `clarifying_question`: set this (and leave `options` empty) only when you truly can't act, like "Which desk do you mean? I don't see a size in the listing." Otherwise null

## Compatibility with the PRD single-plan format

If the backend still expects one `placement`, take the recommended option's new item:

```json
"placement": {"item": "desk_mkt", "x": 1.5, "z": 0.3, "rotation": 0},
"variantName": "Window Desk",
"explanation": "..."
```

## Ranking "which layout is better for studying?"

For a comparison of existing variants, keep `options` as the existing layouts in ranked order (best first), use `explanation` for why each ranks where it does, and set `intent` to `"compare"`.
