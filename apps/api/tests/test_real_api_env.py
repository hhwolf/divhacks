from app.config import Settings
from app.integrations.photon import PhotonAdapter
from app.repo.supabase_store import SupabaseStore


def test_supabase_data_api_url_is_normalized(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ARP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co/rest/v1/")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    s = Settings.from_env()
    assert s.supabase_url == "https://example.supabase.co"
    store = SupabaseStore(s.supabase_url, s.supabase_secret_key)
    assert store._base == "https://example.supabase.co/rest/v1"  # noqa: SLF001


def test_spectrum_project_credentials_alias_photon_live(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ARP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setenv("SPECTRUM_PROJECT_ID", "proj_test")
    monkeypatch.setenv("SPECTRUM_PROJECT_SECRET", "secret_test")
    s = Settings.from_env()
    assert s.spectrum_project_id == "proj_test"
    assert s.photon_api_key == "secret_test"
    assert s.photon_live is True
    adapter = PhotonAdapter(s)
    assert adapter.live is True and adapter.project_id == "proj_test"
