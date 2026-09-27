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


def _supabase_url(raw: str) -> str:
    """Accept either `https://<ref>.supabase.co` or the copied Data API URL ending in `/rest/v1`."""
    return raw.rstrip("/").removesuffix("/rest/v1")


@dataclass(frozen=True)
class Settings:
    mock_mode: bool
    supabase_url: str
    supabase_secret_key: str
    supabase_table: str
    blob_token: str
    gemini_api_key: str
    gemini_model: str
    backboard_api_key: str
    backboard_base_url: str
    spectrum_project_id: str
    photon_api_key: str
    photon_webhook_secret: str
    photon_base_url: str
    photon_from: str
    demo_phone: str
    public_web_url: str
    public_api_url: str
    data_dir: Path

    gemini_fallback_models: tuple[str, ...] = ()
    supabase_publishable_key: str = ""
    housing_data_mode: str = "demo"
    rentcast_api_key: str = ""
    payments_mode: str = "demo"
    payments_database_url: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_connected_account: str = ""
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5186"
    evidence_bucket: str = "housing-evidence"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            mock_mode=_env("MOCK_MODE", "true").lower() in _TRUE,
            supabase_url=_supabase_url(_env("SUPABASE_URL")),
            supabase_secret_key=_env("SUPABASE_SECRET_KEY") or _env("SUPABASE_SERVICE_ROLE_KEY"),
            supabase_table=_env("SUPABASE_TABLE", "arp_documents"),
            blob_token=_env("BLOB_READ_WRITE_TOKEN"),
            gemini_api_key=_env("GEMINI_API_KEY"),
            gemini_model=_env("GEMINI_MODEL", "gemini-3.8-flash"),
            gemini_fallback_models=tuple(m.strip() for m in _env("GEMINI_FALLBACK_MODELS", "gemini-3.7-flash,gemini-3.6-flash,gemini-flash-latest,gemini-3.5-flash-lite,gemini-3.1-flash-lite").split(",") if m.strip()),
            backboard_api_key=_env("BACKBOARD_API_KEY"),
            backboard_base_url=_env("BACKBOARD_BASE_URL", "https://app.backboard.io/api"),
            spectrum_project_id=_env("SPECTRUM_PROJECT_ID") or _env("PHOTON_PROJECT_ID"),
            photon_api_key=_env("PHOTON_API_KEY") or _env("SPECTRUM_PROJECT_SECRET") or _env("PHOTON_PROJECT_SECRET"),
            photon_webhook_secret=_env("PHOTON_WEBHOOK_SECRET"),
            photon_base_url=_env("PHOTON_BASE_URL", "https://spectrum.photon.codes"),
            photon_from=_env("PHOTON_FROM"),
            demo_phone=_env("DEMO_PHONE", "+15555550100"),
            public_web_url=_env("PUBLIC_WEB_URL", "http://localhost:5173"),
            public_api_url=_env("PUBLIC_API_URL", "http://localhost:8000"),
            data_dir=_writable_data_dir(),
            supabase_publishable_key=_env("SUPABASE_PUBLISHABLE_KEY"),
            housing_data_mode=_env("HOUSING_DATA_MODE", "demo"),
            rentcast_api_key=_env("RENTCAST_API_KEY"),
            payments_mode=_env("PAYMENTS_MODE", "demo"),
            payments_database_url=_env("PAYMENTS_DATABASE_URL"),
            stripe_secret_key=_env("STRIPE_SECRET_KEY"),
            stripe_webhook_secret=_env("STRIPE_WEBHOOK_SECRET"),
            stripe_connected_account=_env("STRIPE_CONNECTED_ACCOUNT"),
            allowed_origins=_env("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5186"),
            evidence_bucket=_env("EVIDENCE_BUCKET", "housing-evidence"),
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
    def supabase_live(self) -> bool:
        return bool(self.supabase_url and self.supabase_secret_key)

    @property
    def store_kind(self) -> str:
        """'supabase' (shared Postgres) | 'blob' (Vercel Blob snapshots) | 'json' (local file)."""
        return "supabase" if self.supabase_live else "blob" if self.blob_token else "json"


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
