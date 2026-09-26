"""Settings from environment. Everything runs in mock mode with no variables set; `.env` at the repo root is loaded if present."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

_TRUE = {"1", "true", "yes", "on"}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    mock_mode: bool
    mongodb_uri: str
    mongodb_db: str
    blob_token: str
    gemini_api_key: str
    gemini_model: str
    backboard_api_key: str
    backboard_base_url: str
    photon_api_key: str
    photon_webhook_secret: str
    photon_base_url: str
    photon_from: str
    demo_phone: str
    public_web_url: str
    public_api_url: str
    data_dir: Path

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            mock_mode=_env("MOCK_MODE", "true").lower() in _TRUE,
            mongodb_uri=_env("MONGODB_URI"),
            mongodb_db=_env("MONGODB_DB", "roomplanner"),
            blob_token=_env("BLOB_READ_WRITE_TOKEN"),
            gemini_api_key=_env("GEMINI_API_KEY"),
            gemini_model=_env("GEMINI_MODEL", "gemini-2.5-flash"),
            backboard_api_key=_env("BACKBOARD_API_KEY"),
            backboard_base_url=_env("BACKBOARD_BASE_URL", "https://app.backboard.io/api"),
            photon_api_key=_env("PHOTON_API_KEY"),
            photon_webhook_secret=_env("PHOTON_WEBHOOK_SECRET"),
            photon_base_url=_env("PHOTON_BASE_URL", "https://spectrum.photon.codes"),
            photon_from=_env("PHOTON_FROM"),
            demo_phone=_env("DEMO_PHONE", "+15555550100"),
            public_web_url=_env("PUBLIC_WEB_URL", "http://localhost:5173"),
            public_api_url=_env("PUBLIC_API_URL", "http://localhost:8000"),
            data_dir=_writable_data_dir(),
        )

    def live(self, key: str) -> bool:
        """A service is live when MOCK_MODE is off and its credential is present."""
        return not self.mock_mode and bool(key)

    @property
    def gemini_live(self) -> bool:
        return self.live(self.gemini_api_key)

    @property
    def backboard_live(self) -> bool:
        return self.live(self.backboard_api_key)

    @property
    def photon_live(self) -> bool:
        return self.live(self.photon_api_key)

    @property
    def mongo_live(self) -> bool:
        return bool(self.mongodb_uri)

    @property
    def store_kind(self) -> str:
        """'live' (Mongo) | 'blob' (Vercel Blob, shared across serverless instances) | 'json' (local file)."""
        return "live" if self.mongo_live else "blob" if self.blob_token else "json"


def _writable_data_dir() -> Path:
    """`ARP_DATA_DIR`, else `<repo>/.data`; falls back to /tmp on read-only filesystems (Vercel/Lambda)."""
    candidate = Path(_env("ARP_DATA_DIR") or REPO_ROOT / ".data")
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        return candidate
    except OSError:
        fallback = Path("/tmp/arp-data")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
