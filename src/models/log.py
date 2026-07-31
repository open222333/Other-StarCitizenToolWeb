from datetime import datetime
from src.mongo import get_db


class Log:
    COLLECTION = 'logs'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def create(cls, username: str, action: str, detail: str = '', success: bool = True) -> str:
        result = cls._col().insert_one({
            'username': username,
            'action': action,
            'detail': detail,
            'success': success,
            'created_at': datetime.utcnow()
        })
        return str(result.inserted_id)

    @classmethod
    def find_all(cls, limit: int = 200, offset: int = 0, username: str = '') -> list:
        query = {}
        if username:
            query['username'] = username
        logs = cls._col().find(query, {'_id': 0}).sort('created_at', -1).skip(offset).limit(limit)
        return list(logs)

    @classmethod
    def count(cls, username: str = '') -> int:
        query = {'username': username} if username else {}
        return cls._col().count_documents(query)
