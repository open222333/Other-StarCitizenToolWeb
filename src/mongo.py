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

    # ── 星際公民遊戲主檔（由 tasks/scdata_sync.py 寫入）────────────────
    # (is_current, name_lower) 是 autocomplete 前綴查詢 (^abc) 要走的索引
    for name in ('item_master', 'vehicle_master', 'commodity_master'):
        db[name].create_index([('is_current', ASCENDING), ('name_lower', ASCENDING)])
        db[name].create_index('class_name')
        db[name].create_index('name')
        db[name].create_index('game_version')
    db['item_master'].create_index([('is_current', ASCENDING), ('type', ASCENDING)])
    db['item_master'].create_index([('type', ASCENDING), ('sub_type', ASCENDING)])
    db['item_master'].create_index('manufacturer_code')
    db['vehicle_master'].create_index([('cargo_capacity_scu', DESCENDING)])
    db['commodity_master'].create_index('key')
    for name in ('item_master_versions', 'vehicle_master_versions', 'commodity_master_versions'):
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
