import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures"
SECRETS = (
    "GEMINI_API_KEY", "BACKBOARD_API_KEY", "MONGODB_URI", "BLOB_READ_WRITE_TOKEN",
    "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "SPECTRUM_PROJECT_ID", "SPECTRUM_PROJECT_SECRET",
)


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated JSON store; forces mock mode regardless of the developer's .env."""
    monkeypatch.setenv("ARP_DATA_DIR", str(tmp_path))
    for var in (*SECRETS, "MOCK_MODE"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


@pytest.fixture
def client(data_dir: Path) -> Iterator[TestClient]:
    with TestClient(create_app(Settings.from_env())) as c:
        yield c


@pytest.fixture
def bedroom(client: TestClient) -> dict:
    """{'roomId', 'currentId', 'baseId', 'current'} for a freshly created NYC sample bedroom."""
    d = client.post("/rooms", json={"sample": "nyc-bedroom"}).json()
    return {"roomId": d["room"]["id"], "currentId": d["currentLayout"]["id"], "baseId": d["baseLayout"]["id"], "current": d["currentLayout"]}


def load_fixture(*parts: str) -> dict:
    return json.loads((FIXTURES / Path(*parts)).read_text())
