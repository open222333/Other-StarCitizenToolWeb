import logging

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import OperationFailure

from src import MONGO_URI, MONGO_DB


_client = None
_db = None

# players.star_citizen_id 的唯一索引名稱。
#
# 刻意取一個跟預設 `star_citizen_id_1` 不同的名字：舊環境裡那個名字的索引是
# **非 partial** 的版本，換名字才能讓「舊索引存在 → 砍掉重建」這件事有明確
# 的判斷依據（同名不同 options 的 create_index 在 MongoDB 會直接報
# IndexOptionsConflict）。
_PLAYER_SCID_INDEX = 'players_scid_active_unique'

# 只對「還沒被軟刪除」的玩家做唯一性檢查。
#
# 為什麼要 partial：軟刪除（deleted_at 有值）的文件在非 partial 的唯一索引下
# 仍然佔著這個遊戲ID，導致成員被移除之後那個ID永久卡死 ——
# 註冊前的檢查（會過濾 deleted_at）說「可以用」，接著 insert 撞唯一索引，
# 使用者看到「這個遊戲ID已經被註冊過了」，但後台名冊上查不到這個人，
# 沒有人能解釋、也沒有人能修。
_PLAYER_SCID_PARTIAL = {'deleted_at': None}


def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGO_URI)
        _db = _client[MONGO_DB]
    return _db


def _ensure_player_scid_index(db):
    """建立／遷移 players.star_citizen_id 的 partial 唯一索引。

    舊環境會有一個非 partial 的 `star_citizen_id_1`，必須先砍掉 —— 兩個索引
    同時存在的話，舊的那個照樣會擋住「軟刪除玩家的ID重新註冊」，等於這次修正
    完全沒效果。這裡刻意做成 idempotent（每次啟動都跑，第二次以後什麼都不做），
    因為 ensure_indexes() 是 run.py 每次啟動都呼叫的。

    drop 舊索引期間如果剛好有人註冊，最壞情況是短暫沒有唯一性保護；
    這個規模的公會工具（啟動瞬間、數十人）可以接受，換來的是不需要停機遷移。
    """
    try:
        existing = db['players'].index_information()
    except Exception:  # mongomock 之類的環境可能不支援，直接建就好
        existing = {}

    for name, spec in list(existing.items()):
        if name in ('_id_', _PLAYER_SCID_INDEX):
            continue
        keys = [k for k, _ in spec.get('key', [])]
        if keys == ['star_citizen_id'] and spec.get('unique'):
            # 舊的非 partial 唯一索引（或設定不一致的版本）—— 砍掉重建
            if spec.get('partialFilterExpression') == _PLAYER_SCID_PARTIAL:
                continue
            try:
                db['players'].drop_index(name)
                logging.info('[index] 已移除舊的 players 唯一索引 %s（要換成 partial 版本）', name)
            except OperationFailure as e:
                logging.warning('[index] 移除舊索引 %s 失敗：%s', name, e)

    db['players'].create_index(
        'star_citizen_id', unique=True, name=_PLAYER_SCID_INDEX,
        partialFilterExpression=_PLAYER_SCID_PARTIAL)


_BLUEPRINT_UNIQUE_INDEX = 'blueprints_player_uuid_unique'

# 同一個玩家不該有兩筆「同一張主檔藍圖」的使用中登記。
#
# 只約束「有對應主檔 uuid、且未刪除」的文件：
#   - blueprint_uuid 為 null 的是後台自由輸入的名稱（刻意允許重複）
#   - 軟刪除的要能留著，而且刪掉之後可以重新登記
_BLUEPRINT_UNIQUE_PARTIAL = {
    'deleted_at': None,
    'blueprint_uuid': {'$type': 'string'},
}


def _ensure_blueprint_unique_index(db):
    """建立 (player_id, blueprint_uuid) 的 partial 唯一索引。

    為什麼需要：批量登記是「先查已登記、再 insert_many」的 read-then-write，
    不是原子操作。兩個並發請求（兩個分頁、或 client 對慢回應重試）會同時
    讀到「都還沒登記」然後雙雙寫入 —— 應用層的跳過邏輯擋不住，只有唯一索引擋得住。

    ⚠️ 舊資料可能已經有重複（單筆登記從來沒有防護過）。那種情況建索引會失敗，
    這裡**不會**自動刪資料 —— 改成印出清楚的警告與重複筆數，讓管理員自己決定
    要保留哪一筆。應用層的跳過邏輯在沒有索引時仍然有效（只是擋不住並發）。
    """
    try:
        db['blueprints'].create_index(
            [('player_id', ASCENDING), ('blueprint_uuid', ASCENDING)],
            unique=True, name=_BLUEPRINT_UNIQUE_INDEX,
            partialFilterExpression=_BLUEPRINT_UNIQUE_PARTIAL)
    except OperationFailure as e:
        dupes = _count_blueprint_duplicates(db)
        logging.warning(
            '[index] 無法建立 %s：%s\n'
            '        目前有 %d 組 (玩家, 藍圖) 重複登記，請先清掉多餘的那幾筆'
            '（保留最早的一筆即可），再重啟讓索引建立。'
            ' 在此之前批量登記仍會跳過已登記的，但擋不住並發重複。',
            _BLUEPRINT_UNIQUE_INDEX, e, dupes)


def _count_blueprint_duplicates(db) -> int:
    """有幾組 (player_id, blueprint_uuid) 出現一次以上（給上面的警告用）。"""
    try:
        rows = list(db['blueprints'].aggregate([
            {'$match': {'deleted_at': None, 'blueprint_uuid': {'$type': 'string'}}},
            {'$group': {'_id': {'p': '$player_id', 'b': '$blueprint_uuid'},
                        'n': {'$sum': 1}}},
            {'$match': {'n': {'$gt': 1}}},
            {'$count': 'groups'},
        ], allowDiskUse=True))
        return rows[0]['groups'] if rows else 0
    except Exception:
        return -1


_FLEET_UNIQUE_INDEX = 'fleet_player_vehicle_unique'
# 同一位玩家同一款載具只能有一筆使用中的登記（艘數記在 quantity），
# 軟刪除的不算，刪掉之後可以重新登記。
_FLEET_UNIQUE_PARTIAL = {
    'deleted_at': None,
    'vehicle_uuid': {'$type': 'string'},
}


def _ensure_fleet_unique_index(db):
    """(player_id, vehicle_uuid) 的 partial 唯一索引，擋批量登記的並發重複。

    理由跟 _ensure_blueprint_unique_index 一樣；艦隊是新集合，不會有舊的
    重複資料，但仍包 try，建立失敗只記警告、不讓整個 app 起不來。
    """
    try:
        db['fleet'].create_index(
            [('player_id', ASCENDING), ('vehicle_uuid', ASCENDING)],
            unique=True, name=_FLEET_UNIQUE_INDEX,
            partialFilterExpression=_FLEET_UNIQUE_PARTIAL)
    except OperationFailure as e:
        logging.warning('[index] 無法建立 %s：%s', _FLEET_UNIQUE_INDEX, e)


def ensure_indexes():
    db = get_db()
    db['users'].create_index('username', unique=True)
    db['users'].create_index('template_id')
    db['logs'].create_index([('created_at', DESCENDING)])
    db['logs'].create_index([('username', ASCENDING), ('created_at', DESCENDING)])
    db['device_tokens'].create_index('token', unique=True)
    db['device_tokens'].create_index('username')
    db['device_tokens'].create_index([('updated_at', DESCENDING)], expireAfterSeconds=15552000)  # 180 天 TTL

    # ── 星際公民遊戲主檔（由 tasks/scdata_sync.py 寫入）────────────────
    # (is_current, name_lower) 是 autocomplete 前綴查詢 (^abc) 要走的索引
    for name in ('item_master', 'vehicle_master', 'commodity_master', 'blueprint_master'):
        db[name].create_index([('is_current', ASCENDING), ('name_lower', ASCENDING)])
        db[name].create_index('class_name')
        db[name].create_index('name')
        db[name].create_index('game_version')
    db['item_master'].create_index([('is_current', ASCENDING), ('type', ASCENDING)])
    db['item_master'].create_index([('type', ASCENDING), ('sub_type', ASCENDING)])
    db['item_master'].create_index('manufacturer_code')
    db['vehicle_master'].create_index([('cargo_capacity_scu', DESCENDING)])
    # 艦隊登記／船艦搜尋的篩選欄位
    db['vehicle_master'].create_index([('is_current', ASCENDING), ('manufacturer_code', ASCENDING)])
    db['vehicle_master'].create_index([('is_current', ASCENDING), ('size_class', ASCENDING)])
    db['commodity_master'].create_index('key')
    for name in ('item_master_versions', 'vehicle_master_versions',
                 'commodity_master_versions', 'blueprint_master_versions'):
        db[name].create_index([('item_uuid', ASCENDING), ('game_version', ASCENDING)])

    # UEX 價格與終端
    db['uex_items'].create_index('wiki_uuid')
    db['uex_items'].create_index('id')
    db['uex_items_prices'].create_index('id_item')
    db['uex_items_prices'].create_index('id_terminal')
    db['uex_terminals'].create_index('id')
    db['sync_runs'].create_index([('started_at', DESCENDING)])

    # ── 庫存 ──────────────────────────────────────────────────────────
    # 同一儲位的同物品只能有一筆，入庫靠這個索引做 $inc upsert
    db['inventory'].create_index(
        [('scope_id', ASCENDING), ('owner_type', ASCENDING), ('player', ASCENDING),
         ('location', ASCENDING), ('container', ASCENDING), ('item_id', ASCENDING)],
        unique=True, name='inv_unique')
    db['inventory'].create_index([('scope_id', ASCENDING), ('item_id', ASCENDING)])
    db['inventory'].create_index([('scope_id', ASCENDING), ('location', ASCENDING)])
    db['inventory_log'].create_index([('scope_id', ASCENDING), ('ts', DESCENDING)])
    db['inventory_log'].create_index([('item_id', ASCENDING), ('ts', DESCENDING)])
    db['discord_bindings'].create_index('discord_id', unique=True)
    db['discord_bindings'].create_index([('scope_id', ASCENDING), ('handle', ASCENDING)])

    # ── 玩家名冊 ──────────────────────────────────────────────────────
    # star_citizen_id 就是 inventory/discord_bindings 用的 RSI handle 字串，
    # 唯一索引在這裡做，DuplicateKeyError 由 src/models/player.py 轉成 PlayerError
    _ensure_player_scid_index(db)
    db['players'].create_index('player_name')

    # ── 藍圖名冊 ──────────────────────────────────────────────────────
    db['blueprints'].create_index('player_id')
    db['blueprints'].create_index('name')
    # 玩家名冊指向藍圖主檔的外鍵（可為空 —— 仍允許自由輸入名稱）
    db['blueprints'].create_index('blueprint_uuid')
    _ensure_blueprint_unique_index(db)

    # ── 艦隊名冊（玩家擁有的船／載具，見 src/models/fleet.py）──────────
    db['fleet'].create_index('player_id')
    db['fleet'].create_index('vehicle_uuid')
    _ensure_fleet_unique_index(db)

    # ── 製造藍圖主檔（API 同步，見 src/scdata.py 的 map_blueprint）──
    # 「做出這個物品的所有配方」是主要查詢路徑
    db['blueprint_master'].create_index([('output_item_uuid', ASCENDING),
                                         ('is_current', ASCENDING)])
    db['blueprint_master'].create_index([('is_current', ASCENDING),
                                         ('output_type', ASCENDING)])
    db['blueprint_master'].create_index('key')
