"""玩家名冊模型。

這裡的「玩家」是一份名冊／目錄（暱稱、遊戲ID、Discord 對應），
不是 WMS 的庫存歸屬邏輯 —— 個人庫的持有人一律用 `star_citizen_id`
（RSI handle 字串）當 `src/models/inventory.py` 的 `player` 參數，
兩邊用同一個字串對起來，不另外建立外鍵或重複一套身分系統。

`star_citizen_id` 是唯一索引（見 src/mongo.py ensure_indexes），
新增/註冊時如果重複，Mongo 會丟 DuplicateKeyError，由呼叫端轉成
409 錯誤回給使用者。
"""

import re
from datetime import datetime

import bcrypt
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from src.mongo import get_db


class PlayerError(Exception):
    """預期中的使用者錯誤（例如遊戲ID重複），訊息可直接顯示給使用者。"""


class Player:
    COLLECTION = 'players'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @staticmethod
    def _serialize(doc: dict, include_password: bool = False) -> dict:
        doc = dict(doc)
        doc['_id'] = str(doc['_id'])
        if not include_password:
            doc.pop('password', None)
        return doc

    @classmethod
    def find_all(cls, include_deleted: bool = False) -> list:
        query = {} if include_deleted else {'deleted_at': None}
        rows = cls._col().find(query).sort('player_name', 1)
        return [cls._serialize(r) for r in rows]

    @classmethod
    def find_by_id(cls, player_id: str, include_deleted: bool = False) -> dict | None:
        """`include_deleted=True` 才看得到軟刪除的玩家（給還原用）。"""
        query = {'_id': None}
        try:
            query = {'_id': ObjectId(player_id)}
        except Exception:
            return None
        if not include_deleted:
            query['deleted_at'] = None
        doc = cls._col().find_one(query)
        return cls._serialize(doc) if doc else None

    @classmethod
    def find_by_star_citizen_id(cls, star_citizen_id: str, include_password: bool = False) -> dict | None:
        doc = cls._col().find_one({'star_citizen_id': star_citizen_id, 'deleted_at': None})
        return cls._serialize(doc, include_password=include_password) if doc else None

    @classmethod
    def scids_matching(cls, query: str, limit: int = 100) -> list:
        """暱稱／玩家名稱／遊戲ID 任一含 query 的玩家，回傳他們的遊戲ID 清單。

        給「查詢 › 物品庫存」的複合搜尋用：inventory.player 存的是遊戲ID，
        所以要先把「使用者打的暱稱」翻成一串遊戲ID 才能去撈庫存。

        只回 star_citizen_id 一個欄位 —— 呼叫端只需要拿它當 join key，
        顯示名稱另外走 display_names_by_scid（那支有排掉機密欄位）。
        """
        q = (query or '').strip()
        if not q:
            return []
        # 使用者輸入的 . * ( 不該被當 regex 語法
        pattern = re.escape(q)
        rows = cls._col().find(
            {
                'deleted_at': None,
                '$or': [
                    {'nickname':        {'$regex': pattern, '$options': 'i'}},
                    {'player_name':     {'$regex': pattern, '$options': 'i'}},
                    {'star_citizen_id': {'$regex': pattern, '$options': 'i'}},
                ],
            },
            {'star_citizen_id': 1, '_id': 0},
        ).limit(max(1, min(limit, 500)))
        return [r['star_citizen_id'] for r in rows if r.get('star_citizen_id')]

    @classmethod
    def display_names_by_scid(cls, star_citizen_ids) -> dict:
        """一次查多個遊戲ID的顯示資訊，回傳
        {star_citizen_id: {nickname, player_name, discord_name, discord_id}}。

        給「誰持有這個物品」之類的清單用：inventory.player 存的是 RSI handle
        （＝star_citizen_id），只有代號沒有暱稱，前端要顯示「暱稱（遊戲ID）」
        就得補這一層。刻意做成批次查詢而不是逐列 find_one —— 一個物品可能
        分布在幾十個玩家手上，逐列查就是幾十次 round trip。

        Discord 只有本人在「個人資料」勾了公開才回，否則一律空字串。
        預設不公開（欄位不存在也算沒公開），所以舊資料不會因為新增這個
        功能就突然把每個人的 Discord 攤出來。

        只回這四個欄位，不要整包 player doc：那裡面有 password 跟 notes，
        這支的呼叫端是「給別人看的清單」，不該把它們帶出去。
        """
        scids = [s for s in {str(s) for s in star_citizen_ids if s} if s]
        if not scids:
            return {}
        rows = cls._col().find(
            {'star_citizen_id': {'$in': scids}, 'deleted_at': None},
            {'star_citizen_id': 1, 'nickname': 1, 'player_name': 1,
             'discord_name': 1, 'discord_id': 1, 'discord_public': 1, '_id': 0},
        )
        out = {}
        for r in rows:
            scid = r.get('star_citizen_id')
            if not scid:
                continue
            public = bool(r.get('discord_public'))
            out[scid] = {
                'nickname':     r.get('nickname') or '',
                'player_name':  r.get('player_name') or '',
                'discord_name': (r.get('discord_name') or '') if public else '',
                'discord_id':   (r.get('discord_id') or '') if public else '',
            }
        return out

    @classmethod
    def create(cls, player_name: str, star_citizen_id: str, nickname: str = '',
               discord_name: str = '', discord_id: str = '', notes: str = '',
               password: str = None, discord_public: bool = False) -> str:
        now = datetime.utcnow()
        doc = {
            'player_name':     player_name,
            'star_citizen_id': star_citizen_id,
            'nickname':        nickname,
            'discord_name':    discord_name,
            'discord_id':      discord_id,
            # 預設不公開 —— 聯絡方式的公開範圍要本人明確勾選才成立
            'discord_public':  bool(discord_public),
            'notes':           notes,
            'created_at':      now,
            'updated_at':      now,
            'deleted_at':      None,
        }
        if password:
            doc['password'] = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        try:
            result = cls._col().insert_one(doc)
        except DuplicateKeyError:
            raise PlayerError(f'遊戲ID「{star_citizen_id}」已經被註冊過了')
        return str(result.inserted_id)

    @staticmethod
    def check_password(plain: str, hashed: str | None) -> bool:
        if not hashed:
            return False
        return bcrypt.checkpw(plain.encode(), hashed.encode())

    @classmethod
    def set_password(cls, player_id: str, password: str) -> bool:
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        try:
            result = cls._col().update_one(
                {'_id': ObjectId(player_id), 'deleted_at': None},
                {'$set': {'password': hashed, 'updated_at': datetime.utcnow()}},
            )
        except Exception:
            # player_id 格式不對（不是合法的 ObjectId）—— 呼叫端只需要知道
            # 「沒改到」，不必是 500。呼叫端目前都是後台／玩家自助改密碼，
            # id 來源是 URL 參數或 JWT identity，格式錯就等同「找不到」。
            return False
        return result.matched_count > 0

    @classmethod
    def update(cls, player_id: str, **fields) -> bool:
        """只更新有傳入的欄位（None 表示「不動這個欄位」，呼叫端請先過濾）。

        player_name / star_citizen_id 不接受空字串 —— 清空 star_citizen_id 會讓
        玩家無法登入、個人庫存（inventory.player）變成孤兒，而且沒有還原路徑。
        呼叫端（app/player/view.py）已經先擋一層，這裡是第二道防線。
        """
        set_fields = {k: v for k, v in fields.items() if v is not None}
        for key in ('player_name', 'star_citizen_id'):
            if key in set_fields and not str(set_fields[key]).strip():
                raise PlayerError(f'{key} 不得為空')
        if not set_fields:
            return False
        set_fields['updated_at'] = datetime.utcnow()
        try:
            result = cls._col().update_one(
                {'_id': ObjectId(player_id), 'deleted_at': None},
                {'$set': set_fields},
            )
        except DuplicateKeyError:
            raise PlayerError(f'遊戲ID「{fields.get("star_citizen_id")}」已經被註冊過了')
        return result.matched_count > 0

    @classmethod
    def soft_delete(cls, player_id: str) -> bool:
        """開發原則第 21 條：重要資料不要永久刪除，改用 deleted_at。"""
        try:
            result = cls._col().update_one(
                {'_id': ObjectId(player_id), 'deleted_at': None},
                {'$set': {'deleted_at': datetime.utcnow()}},
            )
        except Exception:
            return False
        return result.matched_count > 0

    @classmethod
    def restore(cls, player_id: str) -> bool:
        """把軟刪除的玩家救回來（`deleted_at` 清成 None）。

        為什麼需要這支：軟刪除本來就是為了「移除成員但保留資料」，但先前
        沒有任何還原路徑 —— 誤刪之後只能進資料庫手改。而個人庫存是用
        `star_citizen_id` 字串對應的（不是 player 文件的 _id），所以還原之後
        那個人原本的庫存與藍圖會自動回到他名下，不需要另外搬資料。

        會擋住「同一個遊戲ID已經有一筆使用中的玩家」的情況：那通常代表對方
        在被移除之後又自助註冊了一次新帳號。這時候把舊的救回來會有兩筆
        使用中的同ID文件（partialFilterExpression 的唯一索引也會拒絕），
        所以這裡先明確擋掉並給出可讀的訊息，而不是讓它變成 500。
        """
        doc = cls.find_by_id(player_id, include_deleted=True)
        if not doc or doc.get('deleted_at') is None:
            return False

        scid = doc.get('star_citizen_id') or ''
        if scid and cls.find_by_star_citizen_id(scid):
            raise PlayerError(
                f'遊戲ID「{scid}」已經有一筆使用中的玩家資料，'
                '請先處理那一筆（例如改名或移除）再還原這筆'
            )

        result = cls._col().update_one(
            {'_id': ObjectId(player_id), 'deleted_at': {'$ne': None}},
            {'$set': {'deleted_at': None, 'updated_at': datetime.utcnow()}},
        )
        return result.matched_count > 0
