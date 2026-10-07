"""玩家頁「艦隊 › JSON 匯入」：匯入 HangarXPLOR 匯出的機庫船單（shiplist.json）。

HangarXPLOR（github.com/dolkensp/HangarXPLOR）是 RSI 機庫頁的瀏覽器擴充功能，
「Download JSON」匯出的是一個陣列，每艘船一筆（同款船買幾艘就有幾筆）：

    {
      "ship_code": "AEGS_Avenger_Titan",      # 廠商代碼 + RSI 船艦頁網址最後一段（- 換成 _）
      "ship_name": "我的小泰坦",               # 有自訂名稱就是自訂名稱，沒有就是官方船名
      "name": "Avenger Titan",                # 機庫上的標題（去掉廠商名）
      "manufacturer_code": "AEGS", "manufacturer_name": "Aegis Dynamics",
      "lookup": "...", "entity_type": "ship",
      "lti": true, "warbond": false,
      "pledge_id": "...", "pledge_name": "...", "pledge_date": "...", "pledge_cost": "$..."
    }

對應到 vehicle_master（依序試，第一個對上的為準）：
  1. ship_code ↔ 主檔 web_url 算出來的同一種代碼（廠商代碼 + 網址最後一段）
  2. 船名寬鬆比對（只留英數字、不分大小寫）：name、ship_code 去掉廠商代碼、lookup，
     對主檔的 name／game_name（也試去掉廠商名的寫法）
同名有好幾筆時優先現行（is_current）的。

匯入規則（重複匯入同一份不會越加越多）：
  - 沒登記過的款式 → 新增，數量 = 這份船單裡的艘數
  - 已登記過 → 數量取「現有」與「船單艘數」較大的（遊戲內用 aUEC 買的船不在機庫，
    所以不會把現有數量改小）
  - 自訂名稱（ship_name 跟官方船名不同的）→ 填進「每艘的區別名稱」空著的位置，
    已經取過名的不覆蓋、同名不重複填
付款、保險（LTI）、禮包資訊都不存。
"""

import re
from datetime import datetime
from urllib.parse import urlparse

from bson import ObjectId

from src.models.fleet import MAX_QUANTITY, UNIT_NAME_MAX, Fleet, clean_unit_names
from src.models.item import VehicleMaster

MAX_IMPORT_ITEMS = 1000
_NON_ALNUM = re.compile(r'[^a-z0-9]+')


class FleetImportError(ValueError):
    pass


def _norm(text) -> str:
    return _NON_ALNUM.sub('', text.lower()) if isinstance(text, str) else ''


def _code_from_url(url, mfr_code) -> str:
    """https://robertsspaceindustries.com/pledge/ships/aegis-avenger/Avenger-Titan → aegs_avenger_titan"""
    if not isinstance(url, str) or not mfr_code:
        return ''
    slug = urlparse(url).path.rstrip('/').rsplit('/', 1)[-1]
    return f'{mfr_code}_{slug.replace("-", "_")}'.lower() if slug else ''


def parse_items(data) -> list:
    """HangarXPLOR 的 JSON（陣列；也接受 {ships: [...]}／{data: [...]}）→ 船的清單。格式不對丟 FleetImportError。"""
    if isinstance(data, dict):
        data = data.get('ships') or data.get('data')
    if not isinstance(data, list):
        raise FleetImportError('檔案格式不對：要是 HangarXPLOR 匯出的 JSON（船的陣列）')
    if len(data) > MAX_IMPORT_ITEMS:
        raise FleetImportError(f'一次最多匯入 {MAX_IMPORT_ITEMS} 艘')
    items = []
    for row in data:
        if not isinstance(row, dict):
            continue
        if row.get('entity_type') not in (None, '', 'ship'):
            continue
        code = row.get('ship_code') if isinstance(row.get('ship_code'), str) else ''
        name = row.get('name') if isinstance(row.get('name'), str) else ''
        if not (code or name):
            continue
        items.append({
            'ship_code': code.strip(),
            'name': name.strip(),
            'ship_name': row.get('ship_name').strip() if isinstance(row.get('ship_name'), str) else '',
            'lookup': row.get('lookup') if isinstance(row.get('lookup'), str) else '',
            'manufacturer_code': row.get('manufacturer_code') if isinstance(row.get('manufacturer_code'), str) else '',
        })
    if not items:
        raise FleetImportError('檔案裡沒有船')
    return items


def _vehicle_index() -> tuple:
    """(代碼 → 主檔, 寬鬆船名 → 主檔)；同一個鍵現行的優先。"""
    by_code, by_name = {}, {}
    fields = {'name': 1, 'game_name': 1, 'web_url': 1, 'manufacturer_code': 1,
              'manufacturer_name': 1, 'is_current': 1, 'class_name': 1}
    rows = sorted(VehicleMaster._col().find({}, fields),
                  key=lambda r: (not r.get('is_current'), len(r.get('class_name') or '')))
    for row in rows:
        if not row.get('name'):
            continue
        code = _code_from_url(row.get('web_url'), row.get('manufacturer_code'))
        if code:
            by_code.setdefault(code, row)
        names = {row.get('name'), row.get('game_name')}
        for mfr in (row.get('manufacturer_name'), row.get('manufacturer_code')):
            for n in list(names):
                if isinstance(n, str) and isinstance(mfr, str) and n.lower().startswith(mfr.lower() + ' '):
                    names.add(n[len(mfr) + 1:])
        for n in names:
            key = _norm(n)
            if key:
                by_name.setdefault(key, row)
    return by_code, by_name


def _match(item, by_code, by_name):
    if item['ship_code'] and item['ship_code'].lower() in by_code:
        return by_code[item['ship_code'].lower()]
    code_tail = item['ship_code'].split('_', 1)[1] if '_' in item['ship_code'] else ''
    for candidate in (item['name'], code_tail, item['lookup']):
        key = _norm(candidate)
        if key and key in by_name:
            return by_name[key]
    return None


def _nickname(item) -> str:
    """ship_name 跟官方船名不一樣才算玩家自訂的名稱。"""
    nick = item['ship_name']
    if not nick:
        return ''
    code_tail = item['ship_code'].split('_', 1)[1] if '_' in item['ship_code'] else ''
    official = {_norm(item['name']), _norm(code_tail), _norm(item['lookup'])} - {''}
    # 全中文之類的名稱正規化後是空字串，一定是玩家自己取的
    if _norm(nick) and _norm(nick) in official:
        return ''
    return nick[:UNIT_NAME_MAX]


def plan(player_id: str, data) -> dict:
    """預覽：每款船匯入幾艘、現有幾艘、匯入後幾艘、自訂名稱；對不到主檔的另外列出。"""
    items = parse_items(data)
    by_code, by_name = _vehicle_index()
    groups, unmatched = {}, {}
    for item in items:
        vehicle = _match(item, by_code, by_name)
        if vehicle is None:
            key = item['ship_code'] or item['name']
            entry = unmatched.setdefault(key, {'name': item['name'] or item['ship_code'],
                                               'ship_code': item['ship_code'], 'count': 0})
            entry['count'] += 1
            continue
        g = groups.setdefault(vehicle['_id'], {
            'vehicle_uuid': vehicle['_id'], 'name': vehicle['name'], 'count': 0,
            'nicknames': [], 'source_names': [],
        })
        g['count'] += 1
        nick = _nickname(item)
        if nick and nick not in g['nicknames']:
            g['nicknames'].append(nick)
        src = item['name'] or item['ship_code']
        if src and src not in g['source_names']:
            g['source_names'].append(src)

    existing = {}
    if groups:
        for row in Fleet._col().find({'player_id': ObjectId(player_id), 'deleted_at': None,
                                      'vehicle_uuid': {'$in': list(groups)}}):
            existing[row['vehicle_uuid']] = row
    masters = VehicleMaster.by_ids(list(groups))
    rows = []
    for uuid, g in groups.items():
        current = existing.get(uuid)
        have = int(current.get('quantity') or 0) if current else 0
        g['existing_quantity'] = have
        g['new_quantity'] = min(max(have, g['count']), MAX_QUANTITY)
        g['fleet_id'] = str(current['_id']) if current else None
        g['name_zh'] = (masters.get(uuid) or {}).get('name_zh')
        rows.append(g)
    rows.sort(key=lambda r: r['name'].lower())
    return {'rows': rows, 'unmatched': sorted(unmatched.values(), key=lambda r: r['name'].lower()),
            'total': len(items)}


def apply(player_id: str, data) -> dict:
    """照 plan 寫入，回傳 {added, updated, unchanged, unmatched}。"""
    result = plan(player_id, data)
    added = updated = unchanged = 0
    now = datetime.utcnow()
    col = Fleet._col()
    for row in result['rows']:
        qty = row['new_quantity']
        if row['fleet_id'] is None:
            col.insert_one({
                'player_id': ObjectId(player_id), 'vehicle_uuid': row['vehicle_uuid'],
                'name': row['name'], 'quantity': qty, 'notes': '',
                'unit_names': clean_unit_names(row['nicknames'], qty),
                'created_at': now, 'updated_at': now, 'deleted_at': None,
            })
            added += 1
            continue
        doc = col.find_one({'_id': ObjectId(row['fleet_id'])}, {'unit_names': 1})
        names = list((doc or {}).get('unit_names') or [])
        names += [''] * (qty - len(names))
        for nick in row['nicknames']:
            if nick in names:
                continue
            try:
                names[names.index('')] = nick
            except ValueError:
                break   # 每艘都已經取過名，不覆蓋
        new_names = clean_unit_names(names, qty)
        if qty == row['existing_quantity'] and new_names == clean_unit_names((doc or {}).get('unit_names') or [], qty):
            unchanged += 1
            continue
        col.update_one({'_id': ObjectId(row['fleet_id'])},
                       {'$set': {'quantity': qty, 'unit_names': new_names, 'updated_at': now}})
        updated += 1
    return {'added': added, 'updated': updated, 'unchanged': unchanged,
            'unmatched': len(result['unmatched']), 'rows': result['rows'], 'unmatched_rows': result['unmatched']}
