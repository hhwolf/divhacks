from app.config import Settings
from app.repo.base import Repository


def make_repository(settings: Settings) -> Repository:
    """Supabase when configured; Vercel Blob when BLOB_READ_WRITE_TOKEN is set; else the local JSON file."""
    if settings.supabase_live:
        from app.repo.supabase_store import SupabaseStore

        return SupabaseStore(settings.supabase_url, settings.supabase_secret_key, settings.supabase_table)
    if settings.blob_token:
        from app.repo.blob_store import BlobStore

        return BlobStore(settings.blob_token)
    from app.repo.json_store import JsonStore

    return JsonStore(settings.data_dir)
