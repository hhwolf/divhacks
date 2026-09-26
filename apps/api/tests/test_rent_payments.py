from fastapi.testclient import TestClient


def test_rent_assessment_uses_scan_area_and_flags_fee(client: TestClient, bedroom: dict) -> None:
    r = client.post(
        "/rent/assess",
        json={
            "roomId": bedroom["roomId"],
            "layoutId": bedroom["currentId"],
            "zip": "10027",
            "askingRent": 1600,
            "depositRequested": 2000,
            "applicationFee": 75,
            "occupancyType": "private_room",
            "declaredIssues": ["rats", "water leak", "bad faucet", "laminate floor"],
        },
    )
    assert r.status_code == 201
    a = r.json()["assessment"]
    assert a["spaceQuality"]["floorAreaSqFt"] > 100
    assert a["spaceQuality"]["usableAreaSqFt"] < a["spaceQuality"]["floorAreaSqFt"]
    assert a["estimatedFairRange"]["low"] < a["estimatedFairRange"]["mid"] < a["estimatedFairRange"]["high"]
    assert a["confidence"] == "medium"
    assert any("Security deposit" in f for f in a["legalFlags"])
    assert any("$20 cap" in f for f in a["legalFlags"])
    assert any("rent-stabilization" in f for f in a["legalFlags"])
    assert client.get(f"/rooms/{bedroom['roomId']}/rent-assessment").json()["assessment"]["id"] == a["id"]


def test_zip_only_rent_assessment_has_lower_confidence(client: TestClient, bedroom: dict) -> None:
    r = client.post("/rent/assess", json={"roomId": bedroom["roomId"], "zip": "11221", "askingRent": 1200, "occupancyType": "private_room"})
    assert r.status_code == 201
    a = r.json()["assessment"]
    assert a["confidence"] == "medium"
    assert any("HPD" in s or "rodent" in s.lower() for s in a["buildingHealthSignals"])


def test_payment_guardrails_block_deposit_and_application_fee(client: TestClient, bedroom: dict) -> None:
    dep = client.post("/payments/quote", json={"roomId": bedroom["roomId"], "purpose": "deposit", "amount": 1800, "rentAmount": 1600}).json()["quote"]
    assert dep["status"] == "blocked"
    assert any("one month" in g for g in dep["guardrails"])

    fee = client.post("/payments/quote", json={"roomId": bedroom["roomId"], "purpose": "application_fee", "amount": 75}).json()["quote"]
    assert fee["status"] == "blocked"
    assert any("$20" in g for g in fee["guardrails"])
    assert client.post("/payments/checkout", json={"purpose": "application_fee", "amount": 75}).status_code == 409


def test_payment_mock_checkout_for_allowed_fee(client: TestClient, bedroom: dict) -> None:
    r = client.post("/payments/checkout", json={"roomId": bedroom["roomId"], "purpose": "application_fee", "amount": 20})
    assert r.status_code == 200
    q = r.json()["quote"]
    assert q["status"] == "mock"
    assert "checkout" in q["stripeCheckoutUrl"]


def test_agent_rent_and_payment_questions_do_not_mutate_current_room(client: TestClient, bedroom: dict) -> None:
    rent = client.post(
        "/agent/request",
        json={"roomId": bedroom["roomId"], "baseLayoutId": bedroom["currentId"], "channel": "app", "text": "I pay $1600 for this room in 10027. Is that fair? rats and leak"},
    ).json()
    assert rent["status"] == "ok"
    assert rent["assessment"]["askingRent"] == 1600
    dep = client.post(
        "/agent/request",
        json={"roomId": bedroom["roomId"], "baseLayoutId": bedroom["currentId"], "channel": "app", "text": "Can I safely send a $500 deposit?"},
    ).json()
    assert dep["status"] == "ok"
    assert dep["quote"]["status"] == "mock"
    assert [l["name"] for l in client.get(f"/rooms/{bedroom['roomId']}").json()["layouts"]] == ["Current Room"]
