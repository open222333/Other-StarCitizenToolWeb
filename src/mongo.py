from pymongo import MongoClient, ASCENDING, DESCENDING
from src import MONGO_URI, MONGO_DB


_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGO_URI)
        _db = _client[MONGO_DB]
    return _db


def ensure_indexes():
    db = get_db()
    db['users'].create_index('username', unique=True)
    db['users'].create_index('template_id')
    db['logs'].create_index([('created_at', DESCENDING)])
    db['logs'].create_index([('username', ASCENDING), ('created_at', DESCENDING)])
    db['device_tokens'].create_index('token', unique=True)
    db['device_tokens'].create_index('username')
    db['device_tokens'].create_index([('updated_at', DESCENDING)], expireAfterSeconds=15552000)  # 180 天 TTL
