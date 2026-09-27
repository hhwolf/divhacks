from app.config import MONGODB_DB, Settings
from app.repo.base import Repository


def make_repository(settings: Settings) -> Repository:
    """MongoDB Atlas when MONGODB_URI is set (always, in live mode); otherwise the local JSON file (mock mode)."""
    if settings.mongo_live:
        from app.repo.mongo_store import MongoStore

        return MongoStore(Settings.reveal(settings.mongodb_uri), MONGODB_DB)
    from app.repo.json_store import JsonStore

    return JsonStore(settings.data_dir)
