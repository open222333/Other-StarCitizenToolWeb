"""成品的基礎數值（給藍圖「品質試算」把倍率換算成實際數值）。

來源是物品主檔 item_master.raw（Wiki API 整筆原始資料，同步時就存了）：
  - description_data：遊戲內說明列出來的數值，例如 Damage Reduction 40%、Temp. Rating -70 / 100 °C
  - clothing（護甲／衣物）：temp_resistance_min／max、damage_resistance_map、radiation_resistance

回傳 {正規化名稱: {name, value, unit}}，正規化名稱＝英文小寫、只留英數字。品質倍率（scunpacked 的
modifier name，例如 Damage Mitigation、Min Temp）用同樣方式正規化後查表；名稱寫法不同的在
ALIASES 對應。查不到的屬性就只顯示倍率。
"""

import re
from typing import Optional

from src.mongo import get_db

_NUMBER = re.compile(r'-?\d[\d,]*(?:\.\d+)?')

#: 品質倍率的屬性名稱 → 物品資料裡可能的名稱（都會正規化）
ALIASES = {
    'Damage Mitigation': ['Damage Reduction'],
    'Min Temp': ['Temp Min', 'Minimum Temperature'],
    'Max Temp': ['Temp Max', 'Maximum Temperature'],
    'Radiation Protection': ['Radiation Capacity'],
    'Radiation Scrub Rate': ['Radiation Dissipation Rate'],
}


def norm(name) -> str:
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())


def _num(text) -> Optional[float]:
    m = _NUMBER.search(text or '')
    return float(m.group(0).replace(',', '')) if m else None


def base_stats(raw: dict) -> dict:
    out: dict = {}

    def put(name, value, unit):
        if value is None:
            return
        out.setdefault(norm(name), {'name': name, 'value': value, 'unit': unit or ''})

    clothing = raw.get('clothing') or raw.get('suit_armor') or {}
    if isinstance(clothing, dict):
        put('Min Temp', clothing.get('temp_resistance_min'), '°C')
        put('Max Temp', clothing.get('temp_resistance_max'), '°C')
        rad = clothing.get('radiation_resistance') or {}
        put('Radiation Protection', rad.get('maximum_radiation_capacity'), 'REM')
        put('Radiation Scrub Rate', rad.get('radiation_dissipation_rate'), 'REM/s')

    for d in raw.get('description_data') or []:
        if not isinstance(d, dict):
            continue
        name, text = d.get('name') or '', str(d.get('value') or '')
        if '/' in text and len(_NUMBER.findall(text)) > 1:
            continue   # 範圍（-70 / 100 °C）上面已經從 clothing 拆開
        value = _num(text)
        if value is None:
            continue
        unit = _NUMBER.sub('', text, count=1).strip()
        put(name, value, unit)

    # 傷害減免：說明沒寫的話用物理傷害倍率換算（0.6 → 減免 40%）
    if norm('Damage Reduction') not in out and isinstance(clothing, dict):
        phys = (clothing.get('damage_resistance_map') or {}).get('physical')
        if isinstance(phys, (int, float)):
            put('Damage Reduction', round((1 - phys) * 100, 2), '%')

    for stat, names in ALIASES.items():
        if norm(stat) in out:
            continue
        for n in names:
            if norm(n) in out:
                out[norm(stat)] = out[norm(n)]
                break
    return out


def for_blueprint(blueprint_uuid: str) -> dict:
    """藍圖產出物品的基礎數值；藍圖沒對到物品或物品沒有原始資料回 {}。"""
    db = get_db()
    bp = db['blueprint_master'].find_one({'_id': str(blueprint_uuid or '')}, {'output_item_uuid': 1})
    if not bp or not bp.get('output_item_uuid'):
        return {}
    item = db['item_master'].find_one({'_id': bp['output_item_uuid']}, {'raw': 1})
    raw = (item or {}).get('raw')
    return base_stats(raw) if isinstance(raw, dict) else {}


def describe(item_id: str) -> Optional[dict]:
    """物品說明與遊戲內說明列出來的數值（raw.description_data 原樣），給「物品資料」的詳細資料用。
    找不到物品回 None。"""
    doc = get_db()['item_master'].find_one(
        {'_id': str(item_id or '')}, {'raw.description_data': 1, 'description_en': 1})
    if not doc:
        return None
    stats = []
    for d in ((doc.get('raw') or {}).get('description_data') or []):
        if isinstance(d, dict) and d.get('name') and d.get('value') not in (None, ''):
            stats.append({'name': str(d['name']).strip(), 'value': str(d['value']).strip()})
    return {'description': doc.get('description_en') or '', 'stats': stats}
