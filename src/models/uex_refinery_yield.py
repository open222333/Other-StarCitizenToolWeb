"""UEX 精煉站產量加成（`uex_refinery_yields`，UEX Corp API 的 /refineries_yields）。

每一列＝某個精煉站（終端）對某種礦物的產量加成百分比，例如 +3 代表在這裡精煉，
產出比基準多 3%。同步在 tasks/scdata_sync.py 的 UEX 項目（UEX_RESOURCES），
資料原樣存進 collection，這裡只負責整理成前端要的精簡格式。

⚠️ 欄位名稱依 UEX 2.0 文件（commodity_name／terminal_name／value…），第一次同步後
請用 db.uex_refinery_yields.findOne() 確認；萬一名稱不同，改 _value／_place 的候選欄位即可。

礦物頁（MiningLookup）用 `base`（去掉 (Ore)／(Raw)／Raw 前綴的小寫名稱，規則同
src/models/uex_commodity.py 的 base_name）跟礦物名稱對上。
"""

from typing import Optional

from src.models.uex_commodity import base_name
from src.mongo import get_db

COLLECTION = 'uex_refinery_yields'

# 產量加成可能出現的欄位（依序取第一個有值的）
_VALUE_FIELDS = ('value', 'yield', 'value_yield', 'bonus')
# 精煉站所在地點：由小到大取第一個有值的
_PLACE_FIELDS = ('space_station_name', 'outpost_name', 'city_name', 'moon_name', 'orbit_name', 'planet_name')


def _value(row: dict) -> Optional[float]:
    for field in _VALUE_FIELDS:
        v = row.get(field)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                continue
    return None


def _place(row: dict) -> str:
    for field in _PLACE_FIELDS:
        if row.get(field):
            return row[field]
    return ''


def list_all() -> list:
    """全部精煉產量加成，精簡成 [{base, commodity, terminal, place, system, value}]，依加成由高到低。"""
    out = []
    for row in get_db()[COLLECTION].find({}, {'_sync': 0}):
        value = _value(row)
        commodity = row.get('commodity_name') or ''
        if value is None or not commodity:
            continue
        out.append({
            'base': base_name(commodity),
            'commodity': commodity,
            'terminal': row.get('terminal_name') or _place(row) or '',
            'place': _place(row),
            'system': row.get('star_system_name') or '',
            'value': value,
        })
    out.sort(key=lambda r: (r['base'], -r['value'], r['terminal']))
    return out
