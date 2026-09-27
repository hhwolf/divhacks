"""Secrets: loaded with pydantic-settings, required outside mock mode, never logged or returned."""

from pathlib import Path

import pytest
from app.config import FRONTEND_ORIGINS, Settings
from app.main import create_app
from fastapi.testclient import TestClient

FAKE = {
    "GEMINI_API_KEY": "gm-secret-123",
    "BACKBOARD_API_KEY": "bb-secret-456",
    "MONGODB_URI": "mongodb://user:pw-secret-789@localhost:1/?serverSelectionTimeoutMS=50",
    "BLOB_READ_WRITE_TOKEN": "vercel_blob_rw_secret_000",
    "STRIPE_SECRET_KEY": "sk_test_secret_111",
    "SPECTRUM_PROJECT_SECRET": "spectrum-secret-222",
}


def test_mock_mode_needs_no_secrets(data_dir: Path) -> None:
    s = Settings.from_env()
    assert s.mock_mode and s.missing_required() == [] and s.store_kind == "json" and not s.blob_live


def test_live_mode_refuses_to_start_without_required_secrets(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setenv("GEMINI_API_KEY", FAKE["GEMINI_API_KEY"])
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "")  # blank counts as unset
    with pytest.raises(RuntimeError) as err:
        create_app(Settings.from_env())
    assert "BACKBOARD_API_KEY" in str(err.value) and "MONGODB_URI" in str(err.value) and "BLOB_READ_WRITE_TOKEN" in str(err.value)
    assert "GEMINI_API_KEY" not in str(err.value) and FAKE["GEMINI_API_KEY"] not in str(err.value)


def test_secrets_never_leak(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_MODE", "false")
    for k, v in FAKE.items():
        monkeypatch.setenv(k, v)
    settings = Settings.from_env()
    assert settings.missing_required() == [] and settings.gemini_live and settings.backboard_live and settings.mongo_live and settings.blob_live
    assert not any(v in repr(settings) or v in str(settings.model_dump()) for v in FAKE.values())
    with TestClient(create_app(settings)) as client:  # clients are built lazily: no network needed for these routes
        health = client.get("/health")
        assert health.json()["mode"] == "live" and health.json()["integrations"]["blob"] == "live"
        for body in (health.text, client.get("/openapi.json").text, client.get("/validation/rules").text):
            assert not any(v in body for v in FAKE.values())
        # CORS: only the frontend origin(s) in live mode
        allowed = client.options("/health", headers={"Origin": FRONTEND_ORIGINS[0], "Access-Control-Request-Method": "GET"})
        assert allowed.headers.get("access-control-allow-origin") == FRONTEND_ORIGINS[0]
        other = client.options("/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
        assert "access-control-allow-origin" not in other.headers


def test_mock_mode_cors_allows_local_dev_servers(client: TestClient) -> None:
    for origin in ("http://localhost:5173", "http://192.168.1.10:5173"):
        r = client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
        assert r.headers.get("access-control-allow-origin") == origin
    assert "access-control-allow-origin" not in client.options("/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}).headers
