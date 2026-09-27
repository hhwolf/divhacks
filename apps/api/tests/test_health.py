from fastapi.testclient import TestClient


def test_health_mock_mode(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["mode"] == "mock"
    assert body["integrations"] == {"gemini": "mock", "backboard": "mock", "photon": "mock", "supabase": "json", "payments": "demo", "housing": "demo", "rentcast": "unavailable", "auth": "demo", "livePayments": "disabled"}


def test_openapi_and_docs_render(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    paths = set(spec["paths"])
    assert {"/rooms", "/layouts/{layout_id}", "/layouts/{a}/compare/{b}", "/furniture/from-link", "/agent/request", "/rent/assess", "/payments/quote", "/webhooks/photon", "/payments/supabase-sync", "/health"} <= paths
    assert client.get("/docs").status_code == 200
