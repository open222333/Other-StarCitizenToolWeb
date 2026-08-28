"""藍圖（Blueprint）名冊模型（規格書第 5 節）。

跟 inventory 系統是分開的兩件事：inventory 管的是「數量會變動的庫存物品」，
blueprint 管的是「某個玩家有沒有解鎖／取得某張藍圖」，是布林狀態，不是數量，
所以沒有整合進 src/models/inventory.py，維持獨立的一張表。

`player_id` 對應 `players` collection 的 `_id`（見 src/models/player.py），
不是 star_citizen_id —— 跟 inventory.player（用 RSI handle 字串）刻意不同，
因為 blueprint 本來就是掛在玩家名冊底下的附屬資料，不需要跟 Discord bot /
UEX 那些系統互相對應。
"""

from datetime import datetime

from bson import ObjectId

from src.mongo import get_db

# 規格書第 5.3 節：取得方式分類
ACQUISITION_METHODS = ['任務', 'NPC 掉落', '寶箱', '探索', '活動', '商店', '聲望獎勵', '特殊事件', '玩家取得', '未知']
# 規格書第 5.2 節：藍圖狀態
UNLOCK_STATUSES = ['locked', 'obtained', 'unlocked', 'unconfirmed', 'outdated']

# 玩家自助登記一律用這個狀態：登記的意思本來就是「我有這張圖」，
# 玩家端不顯示也不選狀態（見 frontend/src/views/MyPlayerView.vue）。
DEFAULT_UNLOCK_STATUS = 'obtained'

# 「誰有這張藍圖」不該列出的狀態。
#
# 這個功能的用意是「找到有這張圖的人，去問他能不能幫做」，所以名冊裡標成
# **未取得**的紀錄出現在結果裡是有害的 —— 問的人會白跑一趟。
# locked 只有管理員從後台設得出來（玩家端一律送 obtained）。
#
# unconfirmed / outdated 刻意**保留**：那些人確實登記過這張圖，只是不確定
# 或版本較舊，仍然值得問一聲。前端會在名字後面標出狀態讓人自己判斷。
HOLDER_HIDDEN_STATUSES = ['locked']


def _redact_contact(holder: dict) -> dict:
    """沒勾「公開 Discord」的人，Discord 欄位一律清空。

    預設不公開（欄位不存在也算沒公開），所以舊資料不會因為新增這個功能
    就突然把每個人的 Discord 攤出來。

    `discord_public` 這個旗標本身不回傳 —— 別人不需要知道你「有沒有選擇
    公開」，只需要知道拿不拿得到聯絡方式。
    """
    holder = dict(holder)
    if not holder.pop('discord_public', False):
        holder['discord_name'] = ''
        holder['discord_id'] = ''
    else:
        holder['discord_name'] = holder.get('discord_name') or ''
        holder['discord_id'] = holder.get('discord_id') or ''
    return holder


class Blueprint:
    COLLECTION = 'blueprints'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @staticmethod
    def _serialize(doc: dict) -> dict:
        doc = dict(doc)
        doc['_id'] = str(doc['_id'])
        if doc.get('player_id'):
            doc['player_id'] = str(doc['player_id'])
        return doc

    @classmethod
    def find_all(cls, player_id: str = '', include_deleted: bool = False) -> list:
        query: dict = {} if include_deleted else {'deleted_at': None}
        if player_id:
            try:
                query['player_id'] = ObjectId(player_id)
            except Exception:
                return []
        rows = cls._col().find(query).sort('name', 1)
        return [cls._serialize(r) for r in rows]

    @classmethod
    def find_by_id(cls, blueprint_id: str) -> dict | None:
        try:
            doc = cls._col().find_one({'_id': ObjectId(blueprint_id), 'deleted_at': None})
        except Exception:
            return None
        return cls._serialize(doc) if doc else None

    @classmethod
    def create(cls, name: str, player_id: str = '', acquisition_method: str = '',
               acquisition_location: str = '', unlock_status: str = 'obtained',
               notes: str = '', blueprint_uuid: str = '') -> str:
        now = datetime.utcnow()
        doc = {
            'name':                   name,
            'player_id':              ObjectId(player_id) if player_id else None,
            'acquisition_method':     acquisition_method,
            'acquisition_location':   acquisition_location,
            'unlock_status':          unlock_status if unlock_status in UNLOCK_STATUSES else DEFAULT_UNLOCK_STATUS,
            'notes':                  notes,
            # 對應 blueprint_master._id（遊戲藍圖主檔，見 src/models/item.py
            # 的 BlueprintMaster）。允許為 None —— 玩家可以自由輸入名稱，
            # 例如主檔還沒同步、或遊戲版本比主檔新。
            'blueprint_uuid':         (blueprint_uuid or '').strip() or None,
            'created_at':             now,
            'updated_at':             now,
            'deleted_at':             None,
        }
        result = cls._col().insert_one(doc)
        return str(result.inserted_id)

    @classmethod
    def update(cls, blueprint_id: str, **fields) -> bool:
        set_fields = {k: v for k, v in fields.items() if v is not None}
        if 'player_id' in set_fields:
            set_fields['player_id'] = ObjectId(set_fields['player_id']) if set_fields['player_id'] else None
        if not set_fields:
            return False
        set_fields['updated_at'] = datetime.utcnow()
        try:
            result = cls._col().update_one(
                {'_id': ObjectId(blueprint_id), 'deleted_at': None},
                {'$set': set_fields},
            )
        except Exception:
            return False
        return result.matched_count > 0

    @classmethod
    def find_holders(cls, query: str = '', limit: int = 50) -> list:
        """依名稱搜尋「誰登記了這張藍圖」，同一張藍圖的持有者聚在一起。

        這是藍圖版的 `Inventory.find_item_locations()`（`/inventory/where`）——
        公會成員互相查詢「誰有這張圖」是刻意提供的功能。

        分組鍵刻意用「blueprint_uuid 有值就用它，否則退回名稱小寫」：
        玩家可以自由輸入藍圖名稱（主檔還沒同步時），那些紀錄沒有 uuid，
        若只用 uuid 分組會全部併成一組 null。

        回傳的欄位刻意不含 `notes` —— 那是玩家寫給自己的備註，不該給別人看。

        標成「未取得」的紀錄不會出現在結果裡，理由見 HOLDER_HIDDEN_STATUSES。
        """
        pipeline: list = [
            {'$match': {
                'deleted_at': None,
                'unlock_status': {'$nin': HOLDER_HIDDEN_STATUSES},
            }},
        ]
        if (query or '').strip():
            import re
            pipeline.append({'$match': {
                'name': {'$regex': re.escape(query.strip()), '$options': 'i'},
            }})

        pipeline += [
            {'$lookup': {
                'from': 'players',
                'localField': 'player_id',
                'foreignField': '_id',
                'as': 'player',
            }},
            {'$unwind': {'path': '$player', 'preserveNullAndEmptyArrays': True}},
            # 已軟刪除的玩家不該出現在別人的查詢結果裡
            {'$match': {'$or': [
                {'player': {'$exists': False}},
                {'player.deleted_at': None},
            ]}},
            {'$group': {
                '_id': {
                    '$ifNull': ['$blueprint_uuid', {'$toLower': '$name'}],
                },
                'name': {'$first': '$name'},
                'blueprint_uuid': {'$first': '$blueprint_uuid'},
                'holders': {'$push': {
                    'player_id': {'$toString': '$player_id'},
                    'nickname': '$player.nickname',
                    'player_name': '$player.player_name',
                    'star_citizen_id': '$player.star_citizen_id',
                    'unlock_status': '$unlock_status',
                    # Discord 只有本人勾了「公開」才給別人看，在 Python 端
                    # 篩掉（見下面的 _redact_contact）。這裡先原樣帶出來是因為
                    # mongomock 對 $group 裡的 $cond 支援不完整，用 aggregation
                    # 做條件遮蔽會在測試環境失效 —— 那種「測試綠燈但線上外洩」
                    # 的失敗方式最糟，所以寧可把判斷放在看得見的地方。
                    'discord_name': '$player.discord_name',
                    'discord_id': '$player.discord_id',
                    'discord_public': '$player.discord_public',
                }},
                'holder_count': {'$sum': 1},
            }},
            {'$sort': {'holder_count': -1, 'name': 1}},
            {'$limit': max(1, min(limit, 200))},
        ]
        groups = list(cls._col().aggregate(pipeline))
        for group in groups:
            group['holders'] = [_redact_contact(h) for h in group.get('holders') or []]
        return groups

    @classmethod
    def soft_delete(cls, blueprint_id: str, player_id: str = '') -> bool:
        """開發原則：重要資料不永久刪除。傳 player_id 時會檢查歸屬（玩家自助刪除用）。"""
        query = {'_id': ObjectId(blueprint_id), 'deleted_at': None}
        if player_id:
            try:
                query['player_id'] = ObjectId(player_id)
            except Exception:
                return False
        try:
            result = cls._col().update_one(query, {'$set': {'deleted_at': datetime.utcnow()}})
        except Exception:
            return False
        return result.matched_count > 0
