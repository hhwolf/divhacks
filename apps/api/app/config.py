"""Settings. Secrets come from the environment (or `.env` at the repo root) through pydantic-settings; everything that is not a
secret is a constant in this module or in rules.json.

The only secrets are the eight keys on `Settings`. They are `SecretStr`, so they never appear in reprs or logs, and no route returns
them. `MOCK_MODE` (default true) is the one operational switch: mock mode runs fully offline with deterministic fixtures and needs no
keys; with `MOCK_MODE=false` the four required keys must be present or startup fails (the Docker image sets `MOCK_MODE=false`).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import PrivateAttr, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")  # into os.environ (never overriding it), so tests can still delenv() a developer's keys

# ---- non-secret config -------------------------------------------------------------------------------------------------
VERSION = "0.2.0"
GEMINI_MODEL = "gemini-2.5-flash"
MONGODB_DB = "roomplanner"
BACKBOARD_BASE_URL = "https://app.backboard.io/api"
# CORS allows only the frontend origin(s). Add "https://<name>.tech" here once the domain is registered; the first entry is also
# the base of the web links returned by the agent.
FRONTEND_ORIGINS: tuple[str, ...] = ("https://adaptive-room-planner.vercel.app",)
DEV_WEB_URL = "http://localhost:5173"
DEV_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+)(:\d+)?$"  # mock mode only
DEMO_USER_ID = "demo"
DEMO_USER_NAME = "Demo renter"
BLOB_ACCESS = "public"  # must match the Vercel Blob store's access mode
LINK_IMPORT_TIMEOUT_S = 10.0
MAX_USDZ_BYTES = 60 * 1024 * 1024
MAX_PHOTO_BYTES = 15 * 1024 * 1024
RECENT_REQUESTS_IN_CONTEXT = 3

REQUIRED_SECRETS = ("GEMINI_API_KEY", "BACKBOARD_API_KEY", "MONGODB_URI", "BLOB_READ_WRITE_TOKEN")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    mock_mode: bool = True
    # required when MOCK_MODE=false
    gemini_api_key: SecretStr | None = None
    backboard_api_key: SecretStr | None = None
    mongodb_uri: SecretStr | None = None
    blob_read_write_token: SecretStr | None = None
    # loaded, never called by this service
    stripe_secret_key: SecretStr | None = None
    stripe_webhook_secret: SecretStr | None = None
    spectrum_project_id: SecretStr | None = None
    spectrum_project_secret: SecretStr | None = None
    # local JSON store / local blob folder (dev and tests only)
    arp_data_dir: Path | None = None

    _data_dir: Path = PrivateAttr()

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_unset(cls, v: object, info) -> object:  # type: ignore[no-untyped-def]
        """`KEY=` in .env means unset, not an empty secret."""
        if isinstance(v, str) and not v.strip():
            return True if info.field_name == "mock_mode" else None
        return v

    def model_post_init(self, _ctx: object) -> None:
        self._data_dir = _writable_data_dir(self.arp_data_dir)

    @classmethod
    def from_env(cls) -> Settings:
        return cls()

    @staticmethod
    def reveal(secret: SecretStr | None) -> str:
        return secret.get_secret_value() if secret else ""

    def missing_required(self) -> list[str]:
        """Names (never values) of required secrets that are absent. Empty in mock mode."""
        if self.mock_mode:
            return []
        return [name for name in REQUIRED_SECRETS if not self.reveal(getattr(self, name.lower()))]

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def gemini_live(self) -> bool:
        return not self.mock_mode and self.gemini_api_key is not None

    @property
    def backboard_live(self) -> bool:
        return not self.mock_mode and self.backboard_api_key is not None

    @property
    def mongo_live(self) -> bool:
        """Storage follows the key in either mode, so tests can run the API on a real mongod."""
        return self.mongodb_uri is not None

    @property
    def blob_live(self) -> bool:
        return self.blob_read_write_token is not None

    @property
    def store_kind(self) -> str:
        return "live" if self.mongo_live else "json"

    @property
    def public_web_url(self) -> str:
        return DEV_WEB_URL if self.mock_mode else FRONTEND_ORIGINS[0]

    @property
    def cors(self) -> dict[str, object]:
        """Kwargs for CORSMiddleware: the frontend origin(s) only; LAN/localhost dev servers are added in mock mode."""
        return {"allow_origins": list(FRONTEND_ORIGINS), "allow_origin_regex": DEV_ORIGIN_REGEX if self.mock_mode else None}


def _writable_data_dir(explicit: Path | None) -> Path:
    """`ARP_DATA_DIR`, else `<repo>/.data`; falls back to /tmp on read-only filesystems (containers, serverless)."""
    candidate = explicit or REPO_ROOT / ".data"
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / f".write-test-{os.getpid()}"
        probe.write_text("ok")
        probe.unlink()
        return candidate
    except OSError:
        fallback = Path("/tmp/arp-data")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
