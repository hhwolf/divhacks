from app.config import Settings
from app.repo.base import Repository


def make_repository(settings: Settings) -> Repository:
    """Mongo when MONGODB_URI is set; Vercel Blob when BLOB_READ_WRITE_TOKEN is set (serverless); else the local JSON file."""
    if settings.mongo_live:
        from app.repo.mongo_store import MongoStore

        return MongoStore(settings.mongodb_uri, settings.mongodb_db)
    if settings.blob_token:
        from app.repo.blob_store import BlobStore

        return BlobStore(settings.blob_token)
    from app.repo.json_store import JsonStore

    return JsonStore(settings.data_dir)
