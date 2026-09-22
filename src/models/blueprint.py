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
from pymongo.errors import BulkWriteError

from src.models.item import escape_regex
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

# 「誰有這張藍圖」每一組最多回傳幾位持有者。
# 總人數另外用 holder_count 帶出去（在 $group 就算好，不受這個截斷影響）。
HOLDERS_PER_GROUP = 50

# 藍圖登記管理列表可點擊排序的欄位（規格書外、全站搜尋優化計畫新增）。
#
# 「取得玩家」故意不在這裡 —— 那一欄顯示的是關聯到 players collection 的
# 玩家名字，不是 blueprints 文件上的純量欄位，排序需要先 $lookup 再排，
# 跟這裡其他欄位的排序方式（直接 .sort()）不是同一件事。等真的有人需要
# 再用 aggregation 加，不要為了「看起來每欄都能排序」而先做一個沒人用的
# join 排序。
SORTABLE_FIELDS = {'name', 'acquisition_method', 'acquisition_location', 'unlock_status'}


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

    # 沒帶 player_id 時（後台「列出全部藍圖」）的硬上限。
    # 原本完全沒有 limit：整個 collection 每次都被撈出來並序列化成 JSON，
    # 隨著登記數成長會變成一次幾 MB 的回應。這個規模的公會短期不會踩到，
    # 但沒有防護的查詢遲早會在最忙的時候變成問題。
    FIND_ALL_MAX = 500

    # 「某一位玩家自己的清單」的上限。遊戲主檔有 1,600+ 張，一個熱衷玩家
    # 全部登記完是有可能的，所以這裡要放到主檔規模以上 —— 用 500 會讓
    # 批量登記頁的「已登記」標記漏掉後面的圖（畫面顯示成可勾選）。
    PLAYER_MAX = 5000

    @classmethod
    def _build_query(cls, *, player_id: str = '', player_ids=None,
                      acquisition_methods=None, acquisition_location: str = '',
                      unlock_statuses=None, query: str = '',
                      include_deleted: bool = False):
        """組出篩選條件；回傳 None 代表條件本身就不可能有結果
        （例如 player_id / player_ids 裡沒有一個是合法的 ObjectId），呼叫端
        應該直接視為「查不到東西」，不用真的送一次注定空手而回的查詢去 Mongo。

        `player_id`（單一）跟 `player_ids`（多選）刻意分開兩個參數而不是共用
        一個、要呼叫端自己包成 list —— 現有呼叫點（app/player/view.py、
        測試）用的是 `player_id=` 這個關鍵字參數，不是 URL query string，
        改成只收 list 會逼所有既有呼叫點都要改寫成 `player_id=[x]`。
        """
        q: dict = {} if include_deleted else {'deleted_at': None}

        ids: list = []
        if player_id:
            try:
                ids.append(ObjectId(player_id))
            except Exception:
                return None
        if player_ids:
            for pid in player_ids:
                try:
                    ids.append(ObjectId(pid))
                except Exception:
                    continue
            if not ids:
                return None
        if ids:
            q['player_id'] = ids[0] if len(ids) == 1 else {'$in': ids}

        if acquisition_methods:
            q['acquisition_method'] = {'$in': list(acquisition_methods)}
        if unlock_statuses:
            q['unlock_status'] = {'$in': list(unlock_statuses)}

        # 取得地點是玩家自由輸入的文字（不是固定列舉），用關鍵字模糊比對，
        # 不做成 distinct 值的多選 —— 否則下拉選單會被大量幾乎一樣但拼法
        # 不同的地點名稱塞爆，反而比一個搜尋框更難用。
        loc = (acquisition_location or '').strip()
        if loc:
            q['acquisition_location'] = {'$regex': escape_regex(loc), '$options': 'i'}

        keyword = (query or '').strip()
        if keyword:
            q['name'] = {'$regex': escape_regex(keyword), '$options': 'i'}

        return q

    @classmethod
    def find_all(cls, player_id: str = '', include_deleted: bool = False,
                 limit: int = 0, offset: int = 0, player_ids=None,
                 acquisition_methods=None, acquisition_location: str = '',
                 unlock_statuses=None, query: str = '',
                 sort_by: str = 'name', sort_dir: int = 1) -> list:
        q = cls._build_query(player_id=player_id, player_ids=player_ids,
                              acquisition_methods=acquisition_methods,
                              acquisition_location=acquisition_location,
                              unlock_statuses=unlock_statuses, query=query,
                              include_deleted=include_deleted)
        if q is None:
            return []
        cap = limit if limit and limit > 0 else cls.FIND_ALL_MAX
        sort_field = sort_by if sort_by in SORTABLE_FIELDS else 'name'
        rows = (cls._col().find(q).sort(sort_field, sort_dir)
                .skip(max(0, offset)).limit(cap))
        return [cls._serialize(r) for r in rows]

    @classmethod
    def count(cls, player_id: str = '', include_deleted: bool = False,
              player_ids=None, acquisition_methods=None,
              acquisition_location: str = '', unlock_statuses=None,
              query: str = '') -> int:
        """跟 find_all 用同一組篩選條件，給分頁的「共 N 筆」用。"""
        q = cls._build_query(player_id=player_id, player_ids=player_ids,
                              acquisition_methods=acquisition_methods,
                              acquisition_location=acquisition_location,
                              unlock_statuses=unlock_statuses, query=query,
                              include_deleted=include_deleted)
        if q is None:
            return 0
        return cls._col().count_documents(q)

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
    def registered_uuids_for_player(cls, player_id: str, uuids=None) -> set:
        """這個玩家已經登記過哪些主檔 uuid（不含已刪除的）。

        給「批量登記」用：畫面要把已登記的標出來並禁止再勾，送出時也要再擋
        一次（畫面資料可能已經過時，或有人直接打 API）。
        `uuids` 給定時只查那幾筆，否則查全部。
        """
        try:
            query = {'player_id': ObjectId(player_id), 'deleted_at': None,
                     'blueprint_uuid': {'$ne': None}}
        except Exception:
            return set()
        if uuids is not None:
            wanted = [u for u in {str(u) for u in uuids if u} if u]
            if not wanted:
                return set()
            query['blueprint_uuid'] = {'$in': wanted}

        return {row['blueprint_uuid'] for row in
                cls._col().find(query, {'blueprint_uuid': 1, '_id': 0})
                if row.get('blueprint_uuid')}

    @classmethod
    def bulk_create_for_player(cls, player_id: str, items,
                               acquisition_method: str = '',
                               acquisition_location: str = '',
                               notes: str = '') -> dict:
        """一次登記多張藍圖，回傳 `{'added': [...], 'skipped': [...]}`。

        `items` 是 `[{'uuid':…, 'name':…}, …]`（名稱一律由呼叫端從主檔取，
        不接受 client 傳來的名稱 —— 理由見 app/player/view.py 的說明）。

        **已登記的會被跳過而不是變成第二筆**：`blueprints` 沒有
        (player_id, blueprint_uuid) 的唯一索引，單筆登記本來就能重複建立，
        而批量登記讓這件事一次放大 50 倍 —— 使用者手滑按兩下就會多出
        一整批重複資料，而「誰有這張圖」的統計會跟著失真。

        `unlock_status` 一律寫死 DEFAULT_UNLOCK_STATUS，跟單筆登記同一個
        理由（玩家端「登記」的語意就是「我有這張圖」）。
        """
        pairs = [(str(item.get('uuid') or '').strip(), item.get('name') or '')
                 for item in (items or [])]
        pairs = [(uuid, name) for uuid, name in pairs if uuid and name]
        if not pairs:
            return {'added': [], 'skipped': []}

        already = cls.registered_uuids_for_player(player_id, [u for u, _ in pairs])
        # 同一次請求裡的重複 uuid 也要去掉，否則一次就寫進兩筆
        seen = set()
        fresh = []
        for uuid, name in pairs:
            if uuid in already or uuid in seen:
                continue
            seen.add(uuid)
            fresh.append((uuid, name))

        if not fresh:
            return {'added': [], 'skipped': [u for u, _ in pairs]}

        now = datetime.utcnow()
        docs = [{
            'name':                 name,
            'player_id':            ObjectId(player_id),
            'acquisition_method':   acquisition_method,
            'acquisition_location': acquisition_location,
            'unlock_status':        DEFAULT_UNLOCK_STATUS,
            'notes':                notes,
            'blueprint_uuid':       uuid,
            'created_at':           now,
            'updated_at':           now,
            'deleted_at':           None,
        } for uuid, name in fresh]

        # ordered=False：讓沒撞到唯一索引的那些照樣寫進去。
        #
        # 上面的「查已登記再跳過」是 read-then-write，不是原子操作 ——
        # 兩個並發請求（兩個分頁、或送出後 client 重試）會同時讀到「都還沒登記」
        # 然後雙雙寫入，正是這支函式想避免的重複。真正的保證來自
        # src/mongo.py 的 (player_id, blueprint_uuid) partial 唯一索引，
        # 撞到的那幾筆在這裡被歸類成 skipped。
        # ordered=True 的話一撞就整批中止，前面成功的還留著、呼叫端卻收到例外。
        added = [uuid for uuid, _ in fresh]
        try:
            cls._col().insert_many(docs, ordered=False)
        except BulkWriteError as err:
            write_errors = err.details.get('writeErrors', [])
            # 撞唯一索引的不算新增，改列進 skipped；其他錯誤照樣往上拋
            if any(e.get('code') != 11000 for e in write_errors):
                raise

            # ⚠️ 用 writeError 的 `index`（這筆是 docs 裡的第幾個）回推 uuid，
            #    不要靠 `keyValue` —— 那是 MongoDB 4.2 以後才有的欄位，
            #    舊版與 mongomock 都不提供。實測過：只看 keyValue 的話，
            #    duplicated 會是空集合，於是「沒寫進去的那筆」被回報成
            #    added（畫面顯示新增 1 張，實際上一筆都沒進去）。
            duplicated = set()
            for e in write_errors:
                pos = e.get('index')
                if isinstance(pos, int) and 0 <= pos < len(docs):
                    duplicated.add(docs[pos]['blueprint_uuid'])
                else:   # 沒有 index 時退回 keyValue（新版 MongoDB 有）
                    uuid = (e.get('keyValue') or {}).get('blueprint_uuid')
                    if uuid:
                        duplicated.add(uuid)

            added = [uuid for uuid in added if uuid not in duplicated]
            already = set(already) | duplicated

        return {'added': added, 'skipped': sorted(already)}

    @classmethod
    def update(cls, blueprint_id: str, **fields) -> bool:
        set_fields = {k: v for k, v in fields.items() if v is not None}
        if 'player_id' in set_fields:
            # ObjectId() 對亂字串會丟 InvalidId —— 放在 try 外面的話，
            # 前端傳了壞掉的 player_id 就是 500，而這是使用者輸入錯誤（400/404）
            try:
                set_fields['player_id'] = (ObjectId(set_fields['player_id'])
                                           if set_fields['player_id'] else None)
            except Exception:
                return False
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
    def find_holders(cls, query: str = '', limit: int = 50,
                     blueprint_uuids=None, player_scid: str = '') -> list:
        """依名稱搜尋「誰登記了這張藍圖」，同一張藍圖的持有者聚在一起。

        這是藍圖版的 `Inventory.find_item_locations()`（`/inventory/where`）——
        公會成員互相查詢「誰有這張圖」是刻意提供的功能。

        分組鍵刻意用「blueprint_uuid 有值就用它，否則退回名稱小寫」：
        玩家可以自由輸入藍圖名稱（主檔還沒同步時），那些紀錄沒有 uuid，
        若只用 uuid 分組會全部併成一組 null。

        回傳的欄位刻意不含 `notes` —— 那是玩家寫給自己的備註，不該給別人看。

        標成「未取得」的紀錄不會出現在結果裡，理由見 HOLDER_HIDDEN_STATUSES。

        blueprint_uuids：呼叫端（app/blueprint/view.py 的 blueprint_holders）
        用「藍圖類型」欄位先解析出來的一組 uuid（見
        BlueprintMaster.uuids_of_type()）。傳 None 代表沒有篩類型；傳空
        陣列代表篩了但那個類型下沒有藍圖，要回空結果——跟
        Inventory.search_filtered() 的 item_ids 是同一套 None/[] 約定，
        呼叫端要留意。自由輸入、沒有 blueprint_uuid 的登記篩類型時天生篩
        不到，是預期行為。

        player_scid：只看這個人登記的（比對 players.star_citizen_id），
        給「查詢」頁的「玩家id」「玩家暱稱」欄位篩選用——兩個欄位選出的
        候選都帶 star_citizen_id，呼叫端一律換算成這個參數，不需要這裡
        另外處理暱稱比對。
        """
        match: dict = {
            'deleted_at': None,
            'unlock_status': {'$nin': HOLDER_HIDDEN_STATUSES},
        }
        if blueprint_uuids is not None:
            if not blueprint_uuids:
                return []
            match['blueprint_uuid'] = {'$in': list(blueprint_uuids)}

        pipeline: list = [{'$match': match}]
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
        ]
        if (player_scid or '').strip():
            pipeline.append({'$match': {'player.star_citizen_id': player_scid.strip()}})

        pipeline += [
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
            # holders 陣列本身也要有上限。
            #
            # 上面的 $limit 限制的是「幾組藍圖」，不是每組裡有幾個人 ——
            # 一張人人都有的熱門藍圖，公會 200 人就會 $push 出 200 筆
            # （每筆還帶 Discord 欄位）。這裡截到 50 人並保留總數
            # （holder_count 在 $group 就算好了，不受這個截斷影響），
            # 前端顯示「50 人以上」就夠用了。
            {'$addFields': {'holders': {'$slice': ['$holders', HOLDERS_PER_GROUP]}}},
        ]
        # allowDiskUse：$group 會把所有 holders 累在記憶體裡，理由同
        # src/models/inventory.py 的 list_stock
        groups = list(cls._col().aggregate(pipeline, allowDiskUse=True))
        for group in groups:
            group['holders'] = [_redact_contact(h) for h in group.get('holders') or []]
        return groups

    @classmethod
    def soft_delete(cls, blueprint_id: str, player_id: str = '') -> bool:
        """開發原則：重要資料不永久刪除。傳 player_id 時會檢查歸屬（玩家自助刪除用）。"""
        # 同 update()：ObjectId() 要包在 try 裡，否則 DELETE /blueprint/abc 是 500
        try:
            query = {'_id': ObjectId(blueprint_id), 'deleted_at': None}
        except Exception:
            return False
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
