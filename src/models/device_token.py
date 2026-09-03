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
    def unregister(cls, token: str, username: str = '') -> bool:
        """移除裝置 token。

        `username` 一定要帶（呼叫端用 JWT identity）—— 只用 token 當條件的話，
        任何登入者（包含玩家自助 token）只要知道／猜到別人的推播 token
        就能把對方的裝置解除註冊，對方從此收不到通知而且完全無感。
        token 本身會出現在 App 日誌、崩潰回報等地方，不能當成秘密。
        """
        query = {'token': token}
        if username:
            query['username'] = username
        result = cls._col().delete_one(query)
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
