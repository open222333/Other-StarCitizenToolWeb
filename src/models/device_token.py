from datetime import datetime
from src.mongo import get_db

PLATFORMS = ('ios', 'android', 'web')


class DeviceToken:
    COLLECTION = 'device_tokens'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def register(cls, username: str, token: str, platform: str, app_version: str = '') -> None:
        """登記或更新裝置推播 token（同一 token 重複登記則更新 username / 時間）。"""
        cls._col().update_one(
            {'token': token},
            {'$set': {
                'username':    username,
                'token':       token,
                'platform':    platform,
                'app_version': app_version,
                'updated_at':  datetime.utcnow(),
            }, '$setOnInsert': {'created_at': datetime.utcnow()}},
            upsert=True,
        )

    @classmethod
    def unregister(cls, token: str) -> bool:
        result = cls._col().delete_one({'token': token})
        return result.deleted_count > 0

    @classmethod
    def unregister_by_username(cls, username: str) -> int:
        """登出時移除該使用者所有裝置 token。"""
        result = cls._col().delete_many({'username': username})
        return result.deleted_count

    @classmethod
    def find_by_username(cls, username: str) -> list:
        """取得使用者所有有效 token（用於發送推播）。"""
        return list(cls._col().find({'username': username}, {'_id': 0}))

    @classmethod
    def find_by_platform(cls, username: str, platform: str) -> list:
        return list(cls._col().find({'username': username, 'platform': platform}, {'_id': 0}))
