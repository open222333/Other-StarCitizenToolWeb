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

from src.models.item import escape_regex
from src.mongo import get_db

USCU_PER_SCU = 1_000_000

# 庫存列表可點擊排序的欄位（全站搜尋優化計畫第 4 項）。
#
# 'total_scu' 故意不在這裡 —— pipeline 裡只有 total_uscu（微 SCU）這個欄位，
# total_scu 是 Python 端才用 uscu_to_scu() 四捨五入算出來的，Mongo 排序看
# 不到它。_SORT_ALIASES 把使用者看到的 'total_scu' 轉成內部真正拿來排序的
# 'total_uscu' —— uscu_to_scu 只是除以常數，用哪個排出來的順序都一樣。
SORTABLE_FIELDS = {'item_name', 'location', 'container', 'quantity', 'total_uscu'}
_SORT_ALIASES = {'total_scu': 'total_uscu'}

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

    @classmethod
    def recent_for_owner(cls, scope_id: str, owner_type: str, player: Optional[str],
                          limit: int = 50) -> list:
        """只看某個歸屬（例如玩家自己的個人庫）的異動紀錄，玩家自助頁面用。"""
        query = {
            'scope_id': str(scope_id), 'owner_type': owner_type,
            'player': player if owner_type == OWNER_PLAYER else None,
        }
        return list(cls._col().find(query, {'_id': 0})
                    .sort('ts', DESCENDING).limit(limit))


class Inventory:
    COLLECTION = 'inventory'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    # ─────────────────────────────────────────────── 查詢

    @classmethod
    def _build_match(cls, scope_id: str, owner_type: str, player: Optional[str],
                      location: str = '', locations=None, container: str = '') -> dict:
        """組出 inventory 原始欄位（非 join 後才有的欄位）的篩選條件。

        `location`（單一，向後相容 bot／既有呼叫點）跟 `locations`（多選，
        後台列表的「位置」篩選用）刻意分開兩個參數，理由跟
        src/models/blueprint.py 的 player_id/player_ids 一樣：既有呼叫點
        是 Python 關鍵字參數，不是 URL query string，不想逼全部改寫。
        兩者都給時 `locations` 優先（後台列表只會傳其中一個）。
        """
        match = _owner_filter(scope_id, owner_type, player)
        if locations:
            match['location'] = {'$in': list(locations)}
        elif location:
            match['location'] = location
        if container:
            match['container'] = {'$regex': escape_regex(container), '$options': 'i'}
        match['quantity'] = {'$gt': 0}
        return match

    @classmethod
    def _name_match_stage(cls, name_query: str) -> list:
        """物品名稱關鍵字（中英文都比對）比對的 $match，給呼叫端接在
        $lookup + $addFields 後面。回傳 list 是因為沒有關鍵字時要接空 list
        （不加這一段 stage），呼叫端用 `pipeline + cls._name_match_stage(q)`
        就好，不用另外判斷要不要加。
        """
        q = (name_query or '').strip()
        if not q:
            return []
        pattern = escape_regex(q)
        return [{'$match': {'$or': [
            {'item_name': {'$regex': pattern, '$options': 'i'}},
            {'item_name_zh': {'$regex': pattern, '$options': 'i'}},
        ]}}]

    @classmethod
    def list_stock(cls, scope_id: str, owner_type: str, player: Optional[str],
                   location: str = '', item_id: str = '',
                   offset: int = 0, limit: int = 50,
                   locations=None, container: str = '', name_query: str = '',
                   sort_by: str = 'item_name', sort_dir: int = ASCENDING) -> tuple:
        """回傳 (該頁資料, 總筆數)。已 join item_master 補上名稱與體積。

        新參數（locations／container／name_query／sort_by／sort_dir）都加在
        既有參數後面，不是插進中間 —— bot/db.py 用位置參數呼叫這支
        （`Inventory.list_stock, SCOPE_ID, owner_type, player, location,
        item_id, offset, limit`），插進中間會讓 item_id/offset/limit 全部
        對錯位置，不會報錯，只會安靜地查錯資料。
        """
        match = cls._build_match(scope_id, owner_type, player, location, locations, container)
        if item_id:
            match['item_id'] = item_id

        base_pipeline = [
            {'$match': match},
            {'$lookup': {'from': 'item_master', 'localField': 'item_id',
                         'foreignField': '_id', 'as': 'item'}},
            {'$unwind': {'path': '$item', 'preserveNullAndEmptyArrays': True}},
            {'$addFields': {
                'item_name': {'$ifNull': ['$item.name', '$item_id']},
                'item_name_zh': '$item.name_zh',
                'item_type': '$item.type',
                # 舊 patch 移除的物品要標出來提醒使用者
                'item_retired': {'$eq': [{'$ifNull': ['$item.is_current', True]}, False]},
                'total_uscu': {'$multiply': [
                    '$quantity', {'$ifNull': ['$item.volume_uscu', 0]}]},
            }},
        ]
        name_match = cls._name_match_stage(name_query)

        if name_match:
            # name_query 篩的是 $lookup 之後才有的欄位，count_documents（只看
            # inventory 原始文件）看不到，只能整條 pipeline 再跑一次 $count——
            # 比 count_documents 貴，所以只有真的有關鍵字時才這樣做。
            total_rows = list(cls._col().aggregate(
                base_pipeline + name_match + [{'$count': 'total'}], allowDiskUse=True))
            total = total_rows[0]['total'] if total_rows else 0
        else:
            total = cls._col().count_documents(match)

        sort_field = _SORT_ALIASES.get(sort_by, sort_by)
        if sort_field not in SORTABLE_FIELDS:
            sort_field = 'item_name'
        # 排序欄位當主鍵，item_name/location 當 tie-breaker（沒被選為排序欄位時）
        # ——維持原本「同排序值時依名稱、位置排」的穩定順序，不會因為換排序欄位
        # 讓同分的列每次重新整理順序都在跳。
        sort_doc = {sort_field: sort_dir}
        if sort_field != 'item_name':
            sort_doc['item_name'] = ASCENDING
        if sort_field != 'location':
            sort_doc['location'] = ASCENDING

        data_pipeline = base_pipeline + name_match + [
            {'$sort': sort_doc},
            {'$skip': offset},
            {'$limit': limit},
            {'$project': {'_id': 0, 'item': 0}},
        ]
        # allowDiskUse：`item_name` 是 $lookup + $addFields 之後才生出來的欄位，
        # 不存在於 inventory 上，所以這個 $sort 不可能走索引 —— 一定是
        # blocking in-memory sort。MongoDB 的記憶體排序上限是 100MB，超過就
        # **直接噴 Sort exceeded memory limit**（整支 GET /inventory/ 打不開，
        # 不是變慢）。允許溢寫磁碟至少讓它還能回應。
        #
        # 這只是保險，不是根治：真正的解法是排序改用 inventory 自己有索引的
        # 欄位（location / item_id），或在 Inventory.adjust() 寫入時就把
        # item_name 反正規化存進文件才能建索引 —— 兩者都會改變顯示順序或
        # 需要資料回填，等到規模真的接近時再處理。
        rows = list(cls._col().aggregate(data_pipeline, allowDiskUse=True))
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
                 location: str = '', locations=None, container: str = '',
                 name_query: str = '') -> dict:
        """算佔用多少 SCU。

        unknown_volume 是「主檔沒有體積資料」的品項數 —— 有值代表 total_scu 低估，
        呼叫端要一併顯示，不能只報總量。

        新參數同樣加在既有參數後面（理由見 list_stock），讓這個總量摘要跟
        列表用同一套篩選條件（後台列表切了篩選之後，上面的「共 N 筆」也要
        跟著變，不能列表被篩過但總量還是全庫的數字）。
        """
        match = cls._build_match(scope_id, owner_type, player, location, locations, container)

        pipeline = [
            {'$match': match},
            {'$lookup': {'from': 'item_master', 'localField': 'item_id',
                         'foreignField': '_id', 'as': 'item'}},
            {'$unwind': {'path': '$item', 'preserveNullAndEmptyArrays': True}},
        ]
        q = (name_query or '').strip()
        if q:
            pattern = escape_regex(q)
            pipeline.append({'$addFields': {
                'item_name': {'$ifNull': ['$item.name', '$item_id']},
                'item_name_zh': '$item.name_zh',
            }})
            pipeline.append({'$match': {'$or': [
                {'item_name': {'$regex': pattern, '$options': 'i'}},
                {'item_name_zh': {'$regex': pattern, '$options': 'i'}},
            ]}})
        pipeline.append({'$group': {
            '_id': None,
            'total_uscu': {'$sum': {'$multiply': [
                '$quantity', {'$ifNull': ['$item.volume_uscu', 0]}]}},
            'units': {'$sum': '$quantity'},
            'lines': {'$sum': 1},
            'unknown_volume': {'$sum': {'$cond': [
                {'$gt': [{'$ifNull': ['$item.volume_uscu', 0]}, 0]}, 0, 1]}},
        }})
        # 這支沒有 $limit（要算整個庫的總量），$lookup + $group 一樣受
        # 100MB 記憶體上限限制，理由同 list_stock。
        rows = list(cls._col().aggregate(pipeline, allowDiskUse=True))
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
    def search_any(cls, scope_id: str, item_ids=None, players=None, locations=None,
                   limit: int = 100) -> list:
        """跨物品的庫存搜尋：只要命中 item_id／player／location 任一組就回傳。

        給「查詢 › 物品庫存」用 —— 使用者在一個框裡打字，可能是物品名、地點、
        別人的暱稱或遊戲ID，呼叫端（app/inventory/view.py 的 search_stock）
        負責先把那串字各自解析成這三組 id/值，這裡只做最後的取聯集。

        為什麼三組都在同一個 $or 裡而不是分三次查再合併：分三次查要在 Python
        端去重，而同一列可能同時命中兩組（例如打「Area18」時某列的地點是
        Area18、持有者暱稱剛好也含 Area18），去重邏輯很容易寫錯。

        三組全空時回空陣列，**不是**回全部 —— 呼叫端沒解析到任何東西就代表
        「搜不到」，回全部會讓使用者以為自己搜到了所有人的庫存。
        """
        ors: list = []
        if item_ids:
            ors.append({'item_id': {'$in': list(item_ids)}})
        if players:
            ors.append({'owner_type': OWNER_PLAYER, 'player': {'$in': list(players)}})
        if locations:
            ors.append({'location': {'$in': list(locations)}})
        if not ors:
            return []

        pipeline = [
            {'$match': {'scope_id': str(scope_id), 'quantity': {'$gt': 0}, '$or': ors}},
            {'$group': {
                '_id': {'item_id': '$item_id', 'owner_type': '$owner_type',
                        'player': '$player', 'location': '$location',
                        'container': '$container'},
                'quantity': {'$sum': '$quantity'},
                'updated_at': {'$max': '$updated_at'},
            }},
            {'$lookup': {'from': 'item_master', 'localField': '_id.item_id',
                         'foreignField': '_id', 'as': 'item'}},
            {'$unwind': {'path': '$item', 'preserveNullAndEmptyArrays': True}},
            {'$addFields': {
                'item_name': {'$ifNull': ['$item.name', '$_id.item_id']},
                'item_name_zh': '$item.name_zh',
                'item_retired': {'$eq': [{'$ifNull': ['$item.is_current', True]}, False]},
            }},
            {'$sort': {'item_name': ASCENDING, 'quantity': DESCENDING}},
            {'$limit': max(1, min(limit, 300))},
        ]
        rows = list(cls._col().aggregate(pipeline))
        return [{
            **row['_id'],
            'quantity':      row['quantity'],
            'updated_at':    row.get('updated_at'),
            'item_name':     row.get('item_name'),
            'item_name_zh':  row.get('item_name_zh'),
            'item_retired':  row.get('item_retired', False),
        } for row in rows]

    @classmethod
    def search_filtered(cls, scope_id: str, item_ids=None, location: str = '',
                        player_scid: str = '', limit: int = 100) -> list:
        """分欄位、AND 語意的庫存搜尋——跟 search_any（OR 取聯集）是不同語意，
        給「查詢 › 物品庫存」拆分欄位版用：使用者從各欄位的自動完成候選裡
        選出精確值（物品／地點／玩家），這裡要求全部有填的條件同時成立
        才算符合，不是任一個符合就算數（那是 search_any 的用途）。

        item_ids 是「物品名稱」「物品類型」兩個欄位在呼叫端（app/inventory/
        view.py 的 search_stock）各自解析出的候選 id——名稱欄位選了就是單一
        item_id，類型欄位選了就是 ItemMaster.ids_of_type() 整組——這裡只單純
        用 $in 篩，不需要知道背後是哪個欄位選出來的。

        item_ids 傳 None 代表「沒有篩物品」（完全略過這個條件）；傳空陣列
        `[]` 代表「篩了但沒有物品符合」（例如選的類型底下沒有物品），要回
        空陣列，不能被當成「沒有篩物品」而查出全部——這個 None／[] 的區別
        很重要，呼叫端要留意。

        全部條件都沒給的話回空陣列，理由同 search_any：沒解析到任何篩選
        條件就代表「查不到」，回全部庫存會讓使用者誤以為自己真的查到了。
        """
        has_filter = item_ids is not None or bool(location) or bool(player_scid)
        if not has_filter:
            return []
        if item_ids is not None and not item_ids:
            return []

        match: dict = {'scope_id': str(scope_id), 'quantity': {'$gt': 0}}
        if item_ids is not None:
            match['item_id'] = {'$in': list(item_ids)}
        if location:
            match['location'] = location
        if player_scid:
            match['owner_type'] = OWNER_PLAYER
            match['player'] = player_scid

        pipeline = [
            {'$match': match},
            {'$group': {
                '_id': {'item_id': '$item_id', 'owner_type': '$owner_type',
                        'player': '$player', 'location': '$location',
                        'container': '$container'},
                'quantity': {'$sum': '$quantity'},
                'updated_at': {'$max': '$updated_at'},
            }},
            {'$lookup': {'from': 'item_master', 'localField': '_id.item_id',
                         'foreignField': '_id', 'as': 'item'}},
            {'$unwind': {'path': '$item', 'preserveNullAndEmptyArrays': True}},
            {'$addFields': {
                'item_name': {'$ifNull': ['$item.name', '$_id.item_id']},
                'item_name_zh': '$item.name_zh',
                'item_retired': {'$eq': [{'$ifNull': ['$item.is_current', True]}, False]},
            }},
            {'$sort': {'item_name': ASCENDING, 'quantity': DESCENDING}},
            {'$limit': max(1, min(limit, 300))},
        ]
        rows = list(cls._col().aggregate(pipeline))
        return [{
            **row['_id'],
            'quantity':      row['quantity'],
            'updated_at':    row.get('updated_at'),
            'item_name':     row.get('item_name'),
            'item_name_zh':  row.get('item_name_zh'),
            'item_retired':  row.get('item_retired', False),
        } for row in rows]

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
             discord_name: str = '', code: str = '') -> dict:
        """把 Discord 帳號綁到某個遊戲ID —— **需要該玩家在網頁產生的綁定碼**。

        為什麼要碼：Discord 帳號跟遊戲帳號之間沒有任何可信連結，所以舊版
        「handle 由使用者自由輸入、直接寫進 DB」等於任何人都能宣稱自己是
        別人 —— 綁完就能用 `/stock scope:我的個人庫` 看光那個人的個人庫、
        用 `/remove` 把它清空（紀錄上的 player 還是被害者）。
        碼由玩家在需要密碼登入的自助頁產生（見 Player.issue_discord_code），
        密碼登入就是那個「證明」。

        綁定成功後會刪掉同一個 handle 在其他 Discord 帳號上的舊綁定：
        一個遊戲ID同時掛在兩個 Discord 帳號上沒有合理用途，
        而且會讓「誰動了我的庫存」查不清楚。
        """
        from src.models.player import Player   # 延遲 import，避免循環依賴

        handle = (handle or '').strip()
        if not 2 <= len(handle) <= 60:
            raise StockError('RSI handle 長度看起來不對（2～60 字元）。')

        player = Player.consume_discord_code(handle, code)
        if not player:
            raise StockError(
                '綁定碼不正確或已過期。請到玩家網頁的「我的資料」按「產生 Discord 綁定碼」，'
                '並確認遊戲ID大小寫與網頁上顯示的一致（碼 10 分鐘內有效）。'
            )

        now = datetime.utcnow()
        doc = cls._col().find_one_and_update(
            {'discord_id': str(discord_id)},
            {'$set': {'handle': handle, 'scope_id': str(scope_id),
                      'discord_name': discord_name, 'updated_at': now},
             '$setOnInsert': {'created_at': now}},
            upsert=True, return_document=ReturnDocument.AFTER,
            projection={'_id': 0},
        )
        cls._col().delete_many({'handle': handle, 'scope_id': str(scope_id),
                                'discord_id': {'$ne': str(discord_id)}})
        return doc

    @classmethod
    def unbind(cls, discord_id: str) -> bool:
        return cls._col().delete_one({'discord_id': str(discord_id)}).deleted_count > 0

    @classmethod
    def require_handle(cls, discord_id: str) -> str:
        binding = cls.get(discord_id)
        if not binding:
            raise StockError('你還沒綁定 RSI handle，先用 `/bind` 綁定。')
        return binding['handle']
