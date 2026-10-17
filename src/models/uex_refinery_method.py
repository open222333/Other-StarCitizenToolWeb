"""UEX 精煉方式（/refineries_methods）與玩家回報的精煉紀錄（/refineries_audits）。

- `uex_refinery_methods`：方法 ID、名稱（例如 Dinyx Solventation），UEX 有給評等就一併帶出。
- `uex_refinery_audits`：玩家回報的每一筆精煉工作——原礦量、產出量、成本、時間、方法、站點、遊戲版本。
  礦物頁用它算「這種礦用每種方式精煉，實際的產出率／每 SCU 成本／每 SCU 時間」（樣本數一併顯示）。
- `uex_refinery_capacities`：精煉站容量，原樣存著，目前只在後台／資料庫查得到。

⚠️ UEX 欄位名稱依文件推測（下面 *_FIELDS 依序取第一個有值的），第一次同步後請用
db.uex_refinery_audits.findOne()／db.uex_refinery_methods.findOne() 確認，名稱不同改候選清單即可。

只用「最新遊戲版本」的紀錄算平均（舊版本的精煉數值可能不同）；紀錄沒有版本欄位就全部一起算。
"""

import re
from typing import Optional

from src.models.uex_commodity import base_name
from src.mongo import get_db

METHODS = 'uex_refinery_methods'
AUDITS = 'uex_refinery_audits'
CAPACITIES = 'uex_refinery_capacities'

_COMMODITY_FIELDS = ('commodity_name', 'commodity')
_METHOD_FIELDS = ('method_name', 'refinery_method_name', 'method')
_INPUT_FIELDS = ('quantity', 'quantity_raw', 'quantity_input', 'quantity_inert', 'scu_input')
_OUTPUT_FIELDS = ('quantity_yield', 'quantity_refined', 'quantity_output', 'yield', 'scu_output')
_COST_FIELDS = ('cost', 'total_cost', 'price', 'value_cost')
# 時間：分鐘欄位優先，其次秒、時（換算成分鐘）
_TIME_FIELDS = (('time_minutes', 1), ('duration_minutes', 1), ('minutes', 1),
                ('time_seconds', 1 / 60), ('duration_seconds', 1 / 60), ('duration', 1 / 60), ('time', 1 / 60),
                ('time_hours', 60), ('hours', 60))
_VERSION_FIELDS = ('game_version', 'version')
# 方法本身的評等（有就帶出）
_RATING_FIELDS = {'yield': ('rating_yield', 'yield'), 'cost': ('rating_cost', 'cost'),
                  'speed': ('rating_speed', 'speed', 'rating_time')}


def _num(value) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(',', ''))
        except ValueError:
            return None
    return None


def _first(row: dict, fields) -> Optional[float]:
    for f in fields:
        v = _num(row.get(f))
        if v is not None:
            return v
    return None


def _first_text(row: dict, fields) -> str:
    for f in fields:
        v = row.get(f)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ''


def _minutes(row: dict) -> Optional[float]:
    for f, factor in _TIME_FIELDS:
        v = _num(row.get(f))
        if v is not None:
            return v * factor
    return None


def _version_key(v: str):
    return [int(p) if p.isdigit() else p for p in re.split(r'[.\-\s]+', v or '') if p]


def list_methods() -> list:
    """精煉方式清單 [{id, name, code, ratings: {yield, cost, speed}}]。"""
    out = []
    for row in get_db()[METHODS].find({}, {'_sync': 0}):
        name = _first_text(row, ('name', 'method_name'))
        if not name:
            continue
        ratings = {k: _first(row, fields) for k, fields in _RATING_FIELDS.items()}
        out.append({'id': row.get('id'), 'name': name, 'code': row.get('code') or '',
                    'ratings': {k: v for k, v in ratings.items() if v is not None}})
    return sorted(out, key=lambda r: r['name'].lower())


def method_stats() -> dict:
    """依礦物×方式彙整玩家回報的精煉紀錄（只取最新遊戲版本）。

    回傳 {'version': '4.x', 'rows': [{base, commodity, method, samples, yield_pct, cost_per_scu, minutes_per_scu}]}：
      yield_pct      ＝ 產出量合計 ÷ 原礦量合計 × 100
      cost_per_scu   ＝ 成本合計 ÷ 原礦量合計（aUEC／每 SCU 原礦）
      minutes_per_scu＝ 時間合計 ÷ 原礦量合計（分鐘／每 SCU 原礦）
    """
    names = {str(m.get('id')): m['name'] for m in list_methods()}
    records = []
    for row in get_db()[AUDITS].find({}, {'_sync': 0}):
        commodity = _first_text(row, _COMMODITY_FIELDS)
        method = _first_text(row, _METHOD_FIELDS) or names.get(str(row.get('id_method') or row.get('id_refinery_method')), '')
        qty_in = _first(row, _INPUT_FIELDS)
        if not commodity or not method or not qty_in or qty_in <= 0:
            continue
        records.append({'commodity': commodity, 'method': method, 'in': qty_in,
                        'out': _first(row, _OUTPUT_FIELDS), 'cost': _first(row, _COST_FIELDS),
                        'minutes': _minutes(row), 'version': _first_text(row, _VERSION_FIELDS)})

    versions = sorted({r['version'] for r in records if r['version']}, key=_version_key)
    latest = versions[-1] if versions else ''
    if latest:
        records = [r for r in records if r['version'] == latest]

    groups: dict = {}
    for r in records:
        g = groups.setdefault((base_name(r['commodity']), r['method']), {
            'commodity': r['commodity'], 'samples': 0,
            'in': 0.0, 'out': 0.0, 'out_in': 0.0, 'cost': 0.0, 'cost_in': 0.0, 'min': 0.0, 'min_in': 0.0})
        g['samples'] += 1
        g['in'] += r['in']
        # 各項只用「有這個欄位」的紀錄算，分母也只算那些紀錄的原礦量
        if r['out'] is not None:
            g['out'] += r['out']; g['out_in'] += r['in']
        if r['cost'] is not None:
            g['cost'] += r['cost']; g['cost_in'] += r['in']
        if r['minutes'] is not None:
            g['min'] += r['minutes']; g['min_in'] += r['in']

    rows = []
    for (base, method), g in groups.items():
        rows.append({
            'base': base, 'commodity': g['commodity'], 'method': method, 'samples': g['samples'],
            'yield_pct': round(g['out'] / g['out_in'] * 100, 1) if g['out_in'] else None,
            'cost_per_scu': round(g['cost'] / g['cost_in'], 1) if g['cost_in'] else None,
            'minutes_per_scu': round(g['min'] / g['min_in'], 2) if g['min_in'] else None,
        })
    rows.sort(key=lambda r: (r['base'], -(r['yield_pct'] or 0), r['method']))
    return {'version': latest, 'rows': rows}
