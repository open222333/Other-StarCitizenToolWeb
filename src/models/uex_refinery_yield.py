"""UEX 精煉站產量加成（`uex_refinery_yields`，UEX Corp API 的 /refineries_yields）。

每一列＝某個精煉站（終端）對某種礦物的產量加成百分比，例如 +3 代表在這裡精煉，
產出比基準多 3%。同步在 tasks/scdata_sync.py 的 UEX 項目（UEX_RESOURCES），
資料原樣存進 collection，這裡只負責整理成前端要的精簡格式。

⚠️ 欄位名稱依 UEX 2.0 文件（commodity_name／terminal_name／value…），第一次同步後
請用 db.uex_refinery_yields.findOne() 確認；萬一名稱不同，改 _value／_place 的候選欄位即可。

另外帶出近 7 天／近 30 天的加成（`week`／`month`，UEX 沒給就是 None），
以及 list_capacities()：`uex_refinery_capacities`（/refineries_capacities）每個精煉站的估算容量百分比
（UEX 給的是估算 %，不是 SCU），礦物頁用終端名稱對上精煉站。

礦物頁（MiningLookup）用 `base`（去掉 (Ore)／(Raw)／Raw 前綴的小寫名稱，規則同
src/models/uex_commodity.py 的 base_name）跟礦物名稱對上。
"""

from typing import Optional

from src.models.uex_commodity import base_name
from src.mongo import get_db

COLLECTION = 'uex_refinery_yields'
CAPACITIES = 'uex_refinery_capacities'

# 產量加成可能出現的欄位（依序取第一個有值的）
_VALUE_FIELDS = ('value', 'yield', 'value_yield', 'bonus')
# 近 7 天／近 30 天的加成（欄位名稱未確認，依序取第一個有值的）
_WEEK_FIELDS = ('value_week', 'value_7d', 'value_7_days', 'average_week', 'avg_week', 'value_weekly')
_MONTH_FIELDS = ('value_month', 'value_30d', 'value_30_days', 'average_month', 'avg_month', 'value_monthly')
# 精煉站估算容量（%）
_CAPACITY_FIELDS = ('capacity_percent', 'capacity_percentage', 'percentage', 'capacity', 'value')
# 終端名稱
_TERMINAL_FIELDS = ('terminal_name', 'refinery_name', 'name')
# 精煉站所在地點：由小到大取第一個有值的
_PLACE_FIELDS = ('space_station_name', 'outpost_name', 'city_name', 'moon_name', 'orbit_name', 'planet_name')


def _value(row: dict, fields=_VALUE_FIELDS) -> Optional[float]:
    for field in fields:
        v = row.get(field)
        if isinstance(v, bool):
            continue
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
    """全部精煉產量加成，精簡成 [{base, commodity, terminal, place, system, value, week, month}]，依加成由高到低。"""
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
            'week': _value(row, _WEEK_FIELDS),
            'month': _value(row, _MONTH_FIELDS),
        })
    out.sort(key=lambda r: (r['base'], -r['value'], r['terminal']))
    return out


def _terminal(row: dict) -> str:
    for field in _TERMINAL_FIELDS:
        v = row.get(field)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ''


def list_capacities() -> list:
    """精煉站估算容量 [{terminal, place, system, capacity_pct}]（%，估算值），依終端名稱排序。"""
    out = []
    for row in get_db()[CAPACITIES].find({}, {'_sync': 0}):
        pct = _value(row, _CAPACITY_FIELDS)
        terminal = _terminal(row) or _place(row)
        if pct is None or not terminal:
            continue
        out.append({
            'terminal': terminal,
            'place': _place(row),
            'system': row.get('star_system_name') or '',
            'capacity_pct': pct,
        })
    out.sort(key=lambda r: r['terminal'].lower())
    return out
