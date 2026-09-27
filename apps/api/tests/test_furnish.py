import pytest
from app.furnish import canned_plan
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from tests.conftest import ROOT

EMPTY = {"name": "Empty", "dimensions": {"l": 3.0, "w": 3.5, "h": 2.6},
         "doors": [{"wall": 2, "offset": 0.3, "width": 0.8, "swing": "in", "hinge": "left"}],
         "windows": [{"wall": 0, "offset": 1.0, "width": 1.0, "sillHeight": 0.9, "height": 1.2}]}


def _empty_room(client: TestClient, **extra: object) -> dict:
    d = client.post("/rooms", json={**EMPTY, **extra}).json()
    assert d["currentLayout"]["items"] == []
    return d


def _furnish(client: TestClient, room_id: str, theme: str, **extra: object) -> dict:
    r = client.post(f"/rooms/{room_id}/furnish", json={"theme": theme, **extra})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize(("theme", "style", "must_have"), [
    ("cozy japandi bedroom", "japandi", {"bed_double", "nightstand"}),
    ("industrial home office", "industrial", {"desk", "chair_desk"}),
    ("boho living room with plants", "boho", {"sofa", "coffee_table", "plant"}),
    ("yoga and meditation", "minimal", {"yoga_mat"}),
])
def test_furnish_empty_room(client: TestClient, theme: str, style: str, must_have: set[str]) -> None:
    d = _empty_room(client)
    out = _furnish(client, d["room"]["id"], theme)
    layout = out["layout"]
    assert out["style"] == style and layout["style"] == style
    assert layout["metrics"]["conflicts"] == 0
    assert must_have <= {i["furnitureId"] for i in layout["items"]}
    assert layout["isCurrent"] is False and layout["parentLayoutId"] == d["currentLayout"]["id"] and layout["createdBy"] == "agent"
    assert out["reply"] and out["placed"]
    names = [l["name"] for l in client.get(f"/rooms/{d['room']['id']}").json()["layouts"]]
    assert names == ["Current Room", layout["name"]]


def test_layout_validates_against_contract(client: TestClient) -> None:
    import json
    schema = json.loads((ROOT / "packages" / "contracts" / "schemas" / "layout.schema.json").read_text())
    out = _furnish(client, _empty_room(client)["room"]["id"], "minimal studio")
    Draft202012Validator(schema).validate(out["layout"])


def test_companions_sit_by_their_anchor(client: TestClient) -> None:
    items = _furnish(client, _empty_room(client)["room"]["id"], "industrial home office")["layout"]["items"]
    desk = next(i for i in items if i["furnitureId"] == "desk")
    chair = next(i for i in items if i["furnitureId"] == "chair_desk")
    assert abs(desk["x"] - chair["x"]) + abs(desk["z"] - chair["z"]) < 0.75
    assert (chair["rotation"] - desk["rotation"]) % 360 == 180  # facing the desk


def test_furnish_keeps_existing_items_and_never_adds_a_second_bed(client: TestClient, bedroom: dict) -> None:
    out = _furnish(client, bedroom["roomId"], "cozy bedroom")
    items = out["layout"]["items"]
    for it in bedroom["current"]["items"]:
        assert it in items
    assert sum(1 for i in items if i["furnitureId"].startswith("bed_")) == 1
    assert out["layout"]["metrics"]["conflicts"] == 0


def test_tiny_room_skips_instead_of_failing(client: TestClient) -> None:
    d = client.post("/rooms", json={"name": "Closet", "dimensions": {"l": 1.5, "w": 1.7, "h": 2.4},
                                    "doors": [{"wall": 3, "offset": 0.2, "width": 0.75, "swing": "in", "hinge": "right"}], "windows": []}).json()
    out = _furnish(client, d["room"]["id"], "boho living room")
    assert out["layout"]["metrics"]["conflicts"] == 0
    assert "Sofa" in out["skipped"] and "Skipped the" in out["reply"] and "sofa" in out["reply"]


def test_repeat_theme_gets_unique_names(client: TestClient) -> None:
    rid = _empty_room(client)["room"]["id"]
    a, b = _furnish(client, rid, "minimal studio"), _furnish(client, rid, "minimal studio")
    assert a["layout"]["name"] == "Minimal studio" and b["layout"]["name"] == "Minimal studio (2)"


def test_errors(client: TestClient) -> None:
    assert client.post("/rooms/nope/furnish", json={"theme": "cozy"}).status_code == 404
    rid = _empty_room(client)["room"]["id"]
    assert client.post(f"/rooms/{rid}/furnish", json={"theme": "   "}).status_code == 422
    assert client.post(f"/rooms/{rid}/furnish", json={"theme": "cozy", "baseLayoutId": "nope"}).status_code == 404


def test_room_profile_sets_purpose_when_theme_has_none(client: TestClient) -> None:
    d = _empty_room(client, spaceTypes=["study"])
    items = _furnish(client, d["room"]["id"], "japandi")["layout"]["items"]
    assert "desk" in {i["furnitureId"] for i in items}


def test_restyle_keeps_purpose_from_hint(client: TestClient) -> None:
    d = _empty_room(client)
    first = _furnish(client, d["room"]["id"], "cozy japandi bedroom")
    out = _furnish(client, d["room"]["id"], "industrial", baseLayoutId=d["currentLayout"]["id"], purposeHint=first["layout"]["requestText"])
    ids = {i["furnitureId"] for i in out["layout"]["items"]}
    assert out["style"] == "industrial" and "bed_double" in ids and "desk" not in ids
    assert out["layout"]["parentLayoutId"] == d["currentLayout"]["id"]


def test_reply_article_counts_and_skips() -> None:
    from app.furnish import compose_reply
    assert compose_reply({"variantName": "Industrial study"}, ["Desk"], []).startswith("Here's an industrial study")
    r = compose_reply({"variantName": "Boho living room"}, ["Sofa", "Potted plant", "Armchair", "Potted plant"], ["Armchair", "Bookshelf"])
    assert r == "Here's a boho living room to start from: sofa, potted plant x2 and armchair. Skipped the bookshelf (not enough room)."


def _png(rgb: tuple[int, int, int], stripes: tuple[int, int, int] | None = None) -> bytes:
    import io

    from PIL import Image, ImageDraw
    img = Image.new("RGB", (120, 80), rgb)
    if stripes:
        d = ImageDraw.Draw(img)
        for x in range(0, 120, 20):
            d.rectangle([x, 0, x + 7, 80], fill=stripes)
    buf = io.BytesIO(); img.save(buf, "PNG"); return buf.getvalue()


def _photos(client: TestClient, room_id: str, images: list[bytes], **form: str) -> dict:
    r = client.post(f"/rooms/{room_id}/furnish/photos", files=[("images", (f"p{i}.png", b, "image/png")) for i, b in enumerate(images)], data=form)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize(("rgb", "stripes", "style"), [
    ((40, 40, 44), None, "industrial"),           # dark concrete + black steel
    ((238, 236, 232), None, "minimal"),           # bright white room
    ((214, 196, 170), None, "japandi"),           # light warm oak and linen
    ((200, 180, 150), (60, 130, 50), "boho"),     # warm room full of plants
])
def test_photo_colours_pick_the_style(client: TestClient, rgb: tuple[int, int, int], stripes: tuple[int, int, int] | None, style: str) -> None:
    out = _photos(client, _empty_room(client)["room"]["id"], [_png(rgb, stripes)])
    assert out["style"] == style and out["layout"]["metrics"]["conflicts"] == 0 and out["placed"]


def test_plant_photos_add_plants_and_typed_words_win(client: TestClient) -> None:
    d = _empty_room(client)
    green = _png((200, 180, 150), (60, 130, 50))
    out = _photos(client, d["room"]["id"], [green, green], theme="japandi bedroom")
    assert out["style"] == "japandi"  # typed style beats the photos' colours
    assert sum(1 for i in out["layout"]["items"] if i["furnitureId"] == "plant") >= 2
    assert "bed_double" in {i["furnitureId"] for i in out["layout"]["items"]}


def test_photo_validation(client: TestClient) -> None:
    rid = _empty_room(client)["room"]["id"]
    bad = client.post(f"/rooms/{rid}/furnish/photos", files=[("images", ("x.png", b"not an image", "image/png"))])
    assert bad.status_code == 422 and "image" in bad.json()["detail"]
    five = client.post(f"/rooms/{rid}/furnish/photos", files=[("images", (f"{i}.png", _png((200, 200, 200)), "image/png")) for i in range(5)])
    assert five.status_code == 422
    assert client.post(f"/rooms/{rid}/furnish/photos").status_code == 422


def test_canned_plan_small_studio_prefers_single_bed() -> None:
    assert canned_plan("studio", floor_m2=10)["items"][0]["item"].startswith("bed_single")
    assert canned_plan("studio", floor_m2=20)["items"][0]["item"].startswith("bed_double")
