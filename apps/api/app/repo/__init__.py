from app.config import Settings
from app.repo.base import Repository


def make_repository(settings: Settings) -> Repository:
    if settings.mongo_live:
        from app.repo.mongo_store import MongoStore

        return MongoStore(settings.mongodb_uri, settings.mongodb_db)
    from app.repo.json_store import JsonStore

    return JsonStore(settings.data_dir)
