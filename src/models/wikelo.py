"""維克洛（Wikelo Emporium）的交易（wikelo_trades）：拿指定物品去換船、武器、護甲…。

資料來源是 Star Citizen Wiki API 的任務（mission_giver=Wikelo）明細，同步項目「維克洛」
（tasks/scdata_sync.py 的 _sync_wikelo；映射見 src/scdata.py 的 map_wikelo_trade）。

每筆：
    {_id: 任務 uuid, title, title_zh, description(_zh), requirements: [{item_uuid, name, amount, max_amount,
     min_scu, max_scu, kind}], rewards: [{item_uuid, name, amount}], reputation_amount（維克洛聲望）,
     prerequisite_groups, prerequisite_uuids, requirement_uuids, reward_uuids, reward_names（小寫）, once_only, shareable, cooldown_seconds, game_version,
     raw, is_current, _sync, first_seen_at}
這輪沒抓到的標 is_current=False（不刪）。
"""

from datetime import datetime
from typing import Optional

from pymongo import ASCENDING, UpdateOne

from src.mongo import get_db

COLLECTION = 'wikelo_trades'
PROJECTION = {'raw': 0, '_sync': 0, 'requirement_uuids': 0, 'reward_uuids': 0, 'reward_names': 0}


def _col():
    return get_db()[COLLECTION]


def save(docs: list, run_id: str, stamp: datetime) -> dict:
    """寫入這一輪的交易（upsert），這輪沒出現的標下架。"""
    col = _col()
    ops = []
    for doc in docs:
        doc = {**doc, 'is_current': True, '_sync': {'run_id': run_id, 'at': stamp}}
        doc.pop('retired_at', None)
        ops.append(UpdateOne({'_id': doc['_id']},
                             {'$set': doc, '$setOnInsert': {'first_seen_at': stamp}, '$unset': {'retired_at': ''}},
                             upsert=True))
    written = 0
    if ops:
        res = col.bulk_write(ops, ordered=False)
        written = res.upserted_count + res.modified_count
    retired = col.update_many({'_sync.run_id': {'$ne': run_id}, 'is_current': {'$ne': False}},
                              {'$set': {'is_current': False, 'retired_at': stamp}}).modified_count
    return {'seen': len(docs), 'written': written, 'retired': retired}


def count_current() -> int:
    return _col().count_documents({'is_current': True})


def _hidden_ids(ids: list) -> set:
    """後台在任務資料庫設成「玩家頁面不顯示」的（交易就是任務，共用那份設定）。"""
    if not ids:
        return set()
    return {d['_id'] for d in get_db()['mission_master'].find(
        {'_id': {'$in': ids}, 'player_visible': False}, {'_id': 1})}


def _zh_by_name(name: str):
    """主檔對不到（uuid 不同、或主檔還沒翻好）時，用英文名稱直接查翻譯：物品名稱、再試載具名稱。"""
    from src.sc_zh import item_name_zh, vehicle_name_zh
    name = (name or '').strip()
    if not name:
        return None
    return item_name_zh(name) or vehicle_name_zh(name=name, game_name=name)


def _attach_names(rows: list) -> list:
    """需求／獎勵的物品補上主檔資料（找不到的維持英文、source=None）：
    name_zh、type、source（vehicle 艦船／item 物品／commodity 商品）、master_name（主檔英文名，給站內「找這個」連結）；
    需求的物品另外標 buyable（UEX 買得到）、blueprint（做得出它的藍圖 uuid），視窗裡的「購買地點」「藍圖」按鈕用。"""
    from src.models import uex_item_price
    from src.models.item import CommodityMaster, ItemMaster, VehicleMaster
    ids = {e.get('item_uuid') for r in rows for k in ('requirements', 'rewards') for e in (r.get(k) or [])
           if e.get('item_uuid')}
    names = {}
    for source, master in (('commodity', CommodityMaster), ('item', ItemMaster), ('vehicle', VehicleMaster)):
        for k, v in master.names_by_ids(ids).items():
            names[k] = {**v, 'source': source}
    item_ids = [k for k, v in names.items() if v['source'] == 'item']
    price, blueprint = {}, {}
    if item_ids:
        tmp = [{'_id': i} for i in item_ids]
        uex_item_price.attach_summaries(tmp)
        price = {t['_id']: (t.get('uex_price') or {}).get('buy_min') for t in tmp}
        for b in get_db()['blueprint_master'].find({'output_item_uuid': {'$in': item_ids}, 'is_current': True},
                                                   {'_id': 1, 'output_item_uuid': 1}).sort('_id', 1):
            blueprint.setdefault(b['output_item_uuid'], b['_id'])
    # 交易標題：任務主檔的中文（翻譯同步後會重新比對，見 Mission.refresh_translations）比同步當下的快照新
    mission_zh = {d['_id']: d for d in get_db()['mission_master'].find(
        {'_id': {'$in': [r['_id'] for r in rows if r.get('_id')]}}, {'title_zh': 1, 'description_zh': 1})}
    for r in rows:
        m = mission_zh.get(r.get('_id')) or {}
        r['title_zh'] = m.get('title_zh') or r.get('title_zh')
        r['description_zh'] = m.get('description_zh') or r.get('description_zh')
        for k in ('requirements', 'rewards'):
            for e in r.get(k) or []:
                hit = names.get(e.get('item_uuid')) or {}
                e['name_zh'] = hit.get('name_zh') or _zh_by_name(e.get('name'))
                e['type'] = hit.get('type')
                e['source'] = hit.get('source')
                e['master_name'] = hit.get('name')
                if k == 'requirements' and hit.get('source') == 'item':
                    e['buyable'] = price.get(e['item_uuid']) is not None
                    e['blueprint'] = blueprint.get(e['item_uuid'])
    return rows


def list_all(query: str = '', visible_only: bool = False) -> list:
    """目前的全部交易（照標題排序）；query＝標題、需求或獎勵物品名稱（中英文）包含這串字。"""
    rows = list(_col().find({'is_current': True}, PROJECTION).sort('title_lower', ASCENDING))
    if visible_only:
        hidden = _hidden_ids([r['_id'] for r in rows])
        rows = [r for r in rows if r['_id'] not in hidden]
    rows = _attach_names(rows)
    q = (query or '').strip().lower()
    if q:
        def hit(r):
            texts = [r.get('title'), r.get('title_zh')] + [
                x for k in ('requirements', 'rewards') for e in (r.get(k) or []) for x in (e.get('name'), e.get('name_zh'))]
            return any(q in (t or '').lower() for t in texts)
        rows = [r for r in rows if hit(r)]
    return rows


def get(trade_id: str, visible_only: bool = False) -> Optional[dict]:
    doc = _col().find_one({'_id': trade_id, 'is_current': True}, PROJECTION)
    if not doc or (visible_only and _hidden_ids([doc['_id']])):
        return None
    return _attach_names([doc])[0]


def _visible(rows: list, visible_only: bool) -> list:
    if not visible_only:
        return rows
    hidden = _hidden_ids([r['_id'] for r in rows])
    return [r for r in rows if r['_id'] not in hidden]


def index(visible_only: bool = False) -> dict:
    """物品／藍圖／艦船列決定要不要顯示「維克洛」按鈕用的索引：
    `{uuids: {uuid: {reward: 幾筆, requirement: 幾筆}}, names: {小寫獎勵名稱: 幾筆}}`（整份很小，前端載一次）。"""
    rows = _visible(list(_col().find({'is_current': True},
                                     {'requirement_uuids': 1, 'reward_uuids': 1, 'reward_names': 1})), visible_only)
    uuids: dict = {}
    names: dict = {}
    for r in rows:
        for kind, key in (('requirement', 'requirement_uuids'), ('reward', 'reward_uuids')):
            for u in r.get(key) or []:
                hit = uuids.setdefault(u, {'reward': 0, 'requirement': 0})
                hit[kind] += 1
        for n in r.get('reward_names') or []:
            names[n] = names.get(n, 0) + 1
    return {'uuids': uuids, 'names': names}


def for_item(uuids=(), names=(), visible_only: bool = False) -> dict:
    """某個物品／藍圖產物／艦船相關的交易：`{reward: [換得到它的交易], requirement: [要交它的交易]}`。
    uuids＝物品 uuid（可多個，例如藍圖的產物），names＝獎勵名稱（艦船用，不分大小寫）。"""
    ids = [u for u in uuids if u]
    lows = [n.strip().lower() for n in names if n and n.strip()]
    reward_or = ([{'reward_uuids': {'$in': ids}}] if ids else []) + ([{'reward_names': {'$in': lows}}] if lows else [])
    out = {'reward': [], 'requirement': []}
    if reward_or:
        out['reward'] = list(_col().find({'is_current': True, '$or': reward_or}, PROJECTION).sort('title_lower', ASCENDING))
    if ids:
        out['requirement'] = list(_col().find({'is_current': True, 'requirement_uuids': {'$in': ids}}, PROJECTION)
                                  .sort('title_lower', ASCENDING))
    for k in out:
        out[k] = _attach_names(_visible(out[k], visible_only))
    return out
