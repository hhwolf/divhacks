from fastapi.testclient import TestClient

SPEC_PATHS = {
    "/rooms", "/rooms/{room_id}", "/rooms/{room_id}/restore", "/layouts/{layout_id}", "/layouts/{layout_id}/fork", "/layouts/{layout_id}/promote",
    "/layouts/{a}/compare/{b}", "/furniture", "/furniture/from-link", "/furniture/from-photo", "/agent/request", "/validation/rules", "/health",
}


def test_health_mock_mode(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["mode"] == "mock" and body["version"] == "0.2.0"
    assert body["integrations"] == {"gemini": "mock", "backboard": "mock", "mongo": "json", "blob": "local", "usdz": "ready"}


def test_openapi_and_docs_render(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert SPEC_PATHS <= set(paths)
    assert {"get", "patch", "delete"} <= set(paths["/rooms/{room_id}"]) and {"get", "put", "patch", "delete"} <= set(paths["/layouts/{layout_id}"])
    assert "multipart/form-data" in paths["/rooms"]["post"]["requestBody"]["content"]
    assert not [p for p in paths if "photon" in p]  # iMessage is out of scope for this service
    assert client.get("/docs").status_code == 200
