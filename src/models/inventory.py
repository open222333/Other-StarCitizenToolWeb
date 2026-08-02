"""庫存模型 —— 倉庫管理的核心邏輯。

這個模組是庫存邏輯的**單一事實來源**：Flask 藍圖（app/inventory/view.py）和
Discord bot（bot/）都呼叫這裡，不各自實作。

兩種歸屬（owner_type）：

| owner_type | player      | 說明         | 誰能寫                                    |
|------------|-------------|--------------|-------------------------------------------|
| `guild`    | `None`      | 公會共享庫   | WMS_OPERATOR_ROLE 角色或 admin/operator   |
| `player`   | RSI handle  | 個人庫       | 只有本人                                  |

併發保護：扣減用 {quantity: {$gte: n}} 當 filter 配 $inc，是單一原子操作。
**不要改成先讀再寫**，那會允許扣成負數。
"""

from datetime import datetime
from typing import Optional

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from src.mongo import get_db

USCU_PER_SCU = 1_000_000

OWNER_GUILD = 'guild'
OWNER_PLAYER = 'player'
OWNER_TYPES = (OWNER_GUILD, OWNER_PLAYER)


def uscu_to_scu(uscu) -> float:
    return round((uscu or 0) / USCU_PER_SCU, 4)


class StockError(Exception):
    """預期中的使用者錯誤（庫存不足、找不到物品、未綁定）。

    訊息會原封不動顯示給使用者，所以要寫成給玩家看的中文，不要塞內部細節。
    """


def _owner_filter(scope_id: str, owner_type: str, player: Optional[str]) -> dict:
    """組出歸屬過濾條件。

    公會庫一律強制 player=None —— 就算呼叫端誤傳 handle，也撈不到別人的個人庫。
    """
    if owner_type not in OWNER_TYPES:
        raise StockError(f'owner_type 必須是 {" 或 ".join(OWNER_TYPES)}')

    return {
        'scope_id': str(scope_id),
        'owner_type': owner_type,
        'player': player if owner_type == OWNER_PLAYER else None,
    }


class InventoryLog:
    """庫存異動稽核日誌。每一筆異動都必須經過這裡。"""

    COLLECTION = 'inventory_log'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def write(cls, **fields) -> str:
        result = cls._col().insert_one({'ts': datetime.utcnow(), **fields})
        return str(result.inserted_id)

    @classmethod
    def recent(cls, scope_id: str, limit: int = 20, item_id: str = '') -> list:
        query: dict = {'scope_id': str(scope_id)}
        if item_id:
            query['item_id'] = item_id
        return list(cls._col().find(query, {'_id': 0})
                    .sort('ts', DESCENDING).limit(limit))


class Inventory:
    COLLECTION = 'inventory'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    # ─────────────────────────────────────────────── 查詢

    @classmethod
    def list_stock(cls, scope_id: str, owner_type: str, player: Optional[str],
                   location: str = '', item_id: str = '',
                   offset: int = 0, limit: int = 50) -> tuple:
        """回傳 (該頁資料, 總筆數)。已 join item_master 補上名稱與體積。"""
        match = _owner_filter(scope_id, owner_type, player)
        if location:
            match['location'] = location
        if item_id:
            match['item_id'] = item_id
        match['quantity'] = {'$gt': 0}

        total = cls._col().count_documents(match)

        pipeline = [
            {'$match': match},
            {'$lookup': {'from': 'item_master', 'localField': 'item_id',
                         'foreignField': '_id', 'as': 'item'}},
            {'$unwind': {'path': '$item', 'preserveNullAndEmptyArrays': True}},
            {'$addFields': {
                'item_name': {'$ifNull': ['$item.name', '$item_id']},
                'item_type': '$item.type',
                # 舊 patch 移除的物品要標出來提醒使用者
                'item_retired': {'$eq': [{'$ifNull': ['$item.is_current', True]}, False]},
                'total_uscu': {'$multiply': [
                    '$quantity', {'$ifNull': ['$item.volume_uscu', 0]}]},
            }},
            {'$sort': {'item_name': ASCENDING, 'location': ASCENDING}},
            {'$skip': offset},
            {'$limit': limit},
            {'$project': {'_id': 0, 'item': 0}},
        ]
        rows = list(cls._col().aggregate(pipeline))
        for row in rows:
            row['total_scu'] = uscu_to_scu(row.get('total_uscu'))
        return rows, total

    @classmethod
    def find_item_locations(cls, scope_id: str, item_id: str, limit: int = 50) -> list:
        """某個物品在這個 scope 內都放在哪（跨公會庫與個人庫）。"""
        pipeline = [
            {'$match': {'scope_id': str(scope_id), 'item_id': item_id,
                        'quantity': {'$gt': 0}}},
            {'$group': {
                '_id': {'owner_type': '$owner_type', 'player': '$player',
                        'location': '$location', 'container': '$container'},
                'quantity': {'$sum': '$quantity'},
                'updated_at': {'$max': '$updated_at'},
            }},
            {'$sort': {'quantity': DESCENDING}},
            {'$limit': limit},
        ]
        rows = list(cls._col().aggregate(pipeline))
        return [{**row['_id'], 'quantity': row['quantity'],
                 'updated_at': row['updated_at']} for row in rows]

    @classmethod
    def capacity(cls, scope_id: str, owner_type: str, player: Optional[str],
                 location: str = '') -> dict:
        """算佔用多少 SCU。

        unknown_volume 是「主檔沒有體積資料」的品項數 —— 有值代表 total_scu 低估，
        呼叫端要一併顯示，不能只報總量。
        """
        match = _owner_filter(scope_id, owner_type, player)
        if location:
            match['location'] = location
        match['quantity'] = {'$gt': 0}

        pipeline = [
            {'$match': match},
            {'$lookup': {'from': 'item_master', 'localField': 'item_id',
                         'foreignField': '_id', 'as': 'item'}},
            {'$unwind': {'path': '$item', 'preserveNullAndEmptyArrays': True}},
            {'$group': {
                '_id': None,
                'total_uscu': {'$sum': {'$multiply': [
                    '$quantity', {'$ifNull': ['$item.volume_uscu', 0]}]}},
                'units': {'$sum': '$quantity'},
                'lines': {'$sum': 1},
                'unknown_volume': {'$sum': {'$cond': [
                    {'$gt': [{'$ifNull': ['$item.volume_uscu', 0]}, 0]}, 0, 1]}},
            }},
        ]
        rows = list(cls._col().aggregate(pipeline))
        if not rows:
            return {'total_scu': 0.0, 'units': 0, 'lines': 0, 'unknown_volume': 0}

        row = rows[0]
        return {
            'total_scu': uscu_to_scu(row['total_uscu']),
            'units': row['units'],
            'lines': row['lines'],
            'unknown_volume': row['unknown_volume'],
        }

    @classmethod
    def distinct_locations(cls, scope_id: str, limit: int = 200) -> list:
        values = cls._col().distinct('location', {'scope_id': str(scope_id)})
        return sorted(v for v in values if v)[:limit]

    # ─────────────────────────────────────────────── 異動

    @classmethod
    def adjust(cls, scope_id: str, owner_type: str, player: Optional[str],
               location: str, container: Optional[str], item_id: str, delta: int,
               actor: str, actor_id: str = '', note: str = '') -> dict:
        """入庫（delta > 0）或出庫（delta < 0）。

        出庫用 quantity >= |delta| 當 filter 配 $inc —— 單一原子操作，
        兩個人同時出庫不會扣成負數，後到的那個會收到「庫存不足」。
        """
        delta = int(delta)
        if delta == 0:
            raise StockError('數量不能是 0。')

        location = (location or '').strip()
        if not location:
            raise StockError('必須指定位置。')

        key = {
            **_owner_filter(scope_id, owner_type, player),
            'location': location,
            'container': (container or '').strip() or None,
            'item_id': item_id,
        }
        now = datetime.utcnow()

        if delta < 0:
            doc = cls._col().find_one_and_update(
                {**key, 'quantity': {'$gte': -delta}},
                {'$inc': {'quantity': delta},
                 '$set': {'updated_at': now, 'updated_by': actor}},
                return_document=ReturnDocument.AFTER,
            )
            if doc is None:
                current = cls._col().find_one(key, {'quantity': 1})
                have = (current or {}).get('quantity', 0)
                raise StockError(f'庫存不足：現有 {have}，要出庫 {-delta}。')
        else:
            doc = cls._col().find_one_and_update(
                key,
                {'$inc': {'quantity': delta},
                 '$set': {'updated_at': now, 'updated_by': actor},
                 '$setOnInsert': {'created_at': now}},
                upsert=True, return_document=ReturnDocument.AFTER,
            )

        InventoryLog.write(
            scope_id=str(scope_id), action='add' if delta > 0 else 'remove',
            actor=actor, actor_id=actor_id, owner_type=owner_type, player=player,
            location=location, container=key['container'], item_id=item_id,
            delta=delta, quantity_after=doc['quantity'], note=note,
        )
        return doc

    @classmethod
    def move(cls, scope_id: str, owner_type: str, player: Optional[str], item_id: str,
             quantity: int, src_location: str, src_container: Optional[str],
             dst_location: str, dst_container: Optional[str],
             actor: str, actor_id: str = '') -> dict:
        """移庫。

        獨立 mongod 不支援多文件交易，所以這裡是補償式的：
        先扣來源（原子且有數量保護），再加到目的地；加失敗就把來源補回去。
        補償寫入也失敗會留一筆 action='move_rollback_failed' 的日誌供人工對帳。

        若日後改用單節點 replica set（--replSet rs0），可以把這段包進 session 換成真交易。
        """
        quantity = int(quantity)
        if quantity <= 0:
            raise StockError('移動數量必須大於 0。')

        src_location = (src_location or '').strip()
        dst_location = (dst_location or '').strip()
        src_container = (src_container or '').strip() or None
        dst_container = (dst_container or '').strip() or None

        if not src_location or not dst_location:
            raise StockError('來源與目的位置都必須指定。')
        if (src_location, src_container) == (dst_location, dst_container):
            raise StockError('來源和目的地是同一個位置。')

        owner = _owner_filter(scope_id, owner_type, player)
        now = datetime.utcnow()

        src_key = {**owner, 'location': src_location,
                   'container': src_container, 'item_id': item_id}
        src_doc = cls._col().find_one_and_update(
            {**src_key, 'quantity': {'$gte': quantity}},
            {'$inc': {'quantity': -quantity},
             '$set': {'updated_at': now, 'updated_by': actor}},
            return_document=ReturnDocument.AFTER,
        )
        if src_doc is None:
            current = cls._col().find_one(src_key, {'quantity': 1})
            have = (current or {}).get('quantity', 0)
            raise StockError(f'來源庫存不足：{src_location} 現有 {have}，要移動 {quantity}。')

        dst_key = {**owner, 'location': dst_location,
                   'container': dst_container, 'item_id': item_id}
        try:
            dst_doc = cls._col().find_one_and_update(
                dst_key,
                {'$inc': {'quantity': quantity},
                 '$set': {'updated_at': now, 'updated_by': actor},
                 '$setOnInsert': {'created_at': now}},
                upsert=True, return_document=ReturnDocument.AFTER,
            )
        except Exception as err:
            try:
                cls._col().update_one(src_key, {'$inc': {'quantity': quantity}})
            except Exception as rollback_err:
                InventoryLog.write(
                    scope_id=str(scope_id), action='move_rollback_failed',
                    actor=actor, actor_id=actor_id, owner_type=owner_type, player=player,
                    location=src_location, container=src_container, item_id=item_id,
                    delta=-quantity, quantity_after=src_doc['quantity'],
                    note=f'寫入目的地失敗且回復失敗，需人工對帳: {err} / {rollback_err}',
                )
                raise StockError(
                    f'移庫失敗且無法自動回復，已記錄到 inventory_log 待人工處理：{err}'
                ) from err
            raise StockError(f'移庫失敗，已回復來源庫存：{err}') from err

        InventoryLog.write(
            scope_id=str(scope_id), action='move',
            actor=actor, actor_id=actor_id, owner_type=owner_type, player=player,
            location=dst_location, container=dst_container, item_id=item_id,
            delta=quantity, quantity_after=dst_doc['quantity'],
            note=f'從 {src_location}' + (f' / {src_container}' if src_container else '') + ' 移入',
        )
        return {'src': src_doc, 'dst': dst_doc}


class DiscordBinding:
    """Discord 使用者 ↔ RSI handle 的自助綁定。"""

    COLLECTION = 'discord_bindings'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def get(cls, discord_id: str) -> Optional[dict]:
        return cls._col().find_one({'discord_id': str(discord_id)}, {'_id': 0})

    @classmethod
    def bind(cls, discord_id: str, handle: str, scope_id: str,
             discord_name: str = '') -> dict:
        handle = (handle or '').strip()
        if not 2 <= len(handle) <= 60:
            raise StockError('RSI handle 長度看起來不對（2～60 字元）。')

        now = datetime.utcnow()
        return cls._col().find_one_and_update(
            {'discord_id': str(discord_id)},
            {'$set': {'handle': handle, 'scope_id': str(scope_id),
                      'discord_name': discord_name, 'updated_at': now},
             '$setOnInsert': {'created_at': now}},
            upsert=True, return_document=ReturnDocument.AFTER,
            projection={'_id': 0},
        )

    @classmethod
    def unbind(cls, discord_id: str) -> bool:
        return cls._col().delete_one({'discord_id': str(discord_id)}).deleted_count > 0

    @classmethod
    def require_handle(cls, discord_id: str) -> str:
        binding = cls.get(discord_id)
        if not binding:
            raise StockError('你還沒綁定 RSI handle，先用 `/bind` 綁定。')
        return binding['handle']
