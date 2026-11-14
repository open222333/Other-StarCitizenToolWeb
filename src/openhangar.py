"""Open Hangar（https://openhangar.space）的商店歷史：抓取與欄位映射。

只用一個公開端點 GET /api/store/catalog（不需要登入），回傳整份 JSON，用到的欄位：

history: {船名: [[開始ms, 結束ms|null, 價格USD, 種類, 當時標準價|null], ...]}
    從 2021-11 起每段上架期間。種類：S＝一般單買、W＝Warbond、U＝（官方沒說明，原樣保留代碼）
avail:   {船名: {avail: always/often/sometimes/rarely/hardly/events/new, firstSold: ms}}
makers:  {船名: 廠商}
items:   目前商店品項；k == 'ccus' 的升級品項帶 toShipId（＝RSI 商店的船 id）與 hk（＝history 的船名），
         用來把歷史對到 rsi_ships

資料授權 CC BY 4.0，畫面上用到要標註「資料來源：Open Hangar」。
可信度：Open Hangar 是第三方整理的歷史紀錄，跟 RSI 商店重疊的期間以 RSI（src/models/ccu.py）為準。
"""

from datetime import datetime, timezone

CATALOG_URL = 'https://openhangar.space/api/store/catalog'
SOURCE = 'openhangar'
CREDIBILITY = '歷史紀錄'
ATTRIBUTION = '資料來源：Open Hangar（openhangar.space，CC BY 4.0）'

#: history 的種類代碼 → 欄位值、中文
SALE_TYPES = {'S': ('standard', '單買'), 'W': ('warbond', 'Warbond'), 'U': ('code_u', '其他（U）')}

AVAIL_LABELS = {'always': '常駐', 'often': '常出現', 'sometimes': '偶爾', 'rarely': '少見',
                'hardly': '極少見', 'events': '只在活動', 'new': '新船'}


class OpenHangarError(Exception):
    pass


def fetch_catalog(client) -> dict:
    try:
        resp = client.get(CATALOG_URL)
    except Exception as err:  # 連線錯誤、逾時
        raise OpenHangarError(f'連不到 Open Hangar：{err}') from err
    if resp.status_code != 200:
        raise OpenHangarError(f'Open Hangar 回 HTTP {resp.status_code}')
    try:
        data = resp.json()
    except ValueError as err:
        raise OpenHangarError('Open Hangar 回的不是 JSON') from err
    if not isinstance(data, dict) or not isinstance(data.get('history'), dict):
        raise OpenHangarError('Open Hangar 回傳格式不對（沒有 history）')
    return data


def ms_to_dt(ms):
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000, timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _num(v):
    try:
        return round(float(v), 2) if v is not None else None
    except (TypeError, ValueError):
        return None


def map_periods(rows) -> list:
    """[[start, end, price, code, std], ...] → [{start, end, price, msrp, sale_type, code}]，照開始時間排序。"""
    out = []
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) < 4:
            continue
        start = ms_to_dt(row[0])
        if start is None:
            continue
        code = str(row[3] or '')
        out.append({'start': start, 'end': ms_to_dt(row[1]), 'price': _num(row[2]),
                    'msrp': _num(row[4]) if len(row) > 4 else None,
                    'sale_type': SALE_TYPES.get(code, (f'code_{code.lower()}', code))[0], 'code': code})
    out.sort(key=lambda p: (p['start'], p['code']))
    return out


def ship_ids_from_items(items) -> dict:
    """目前的升級品項：history 船名 → RSI 船 id。"""
    out = {}
    for it in items or []:
        if isinstance(it, dict) and it.get('k') == 'ccus' and it.get('hk') and it.get('toShipId') is not None:
            out.setdefault(it['hk'], it['toShipId'])
    return out


def map_history(data: dict) -> list:
    """整份 catalog → 每艘船一筆 {name, manufacturer, avail, first_sold_at, rsi_id, periods, ...}。"""
    avail = data.get('avail') or {}
    makers = data.get('makers') or {}
    ids = ship_ids_from_items(data.get('items'))
    out = []
    for name, rows in (data.get('history') or {}).items():
        periods = map_periods(rows)
        if not name or not periods:
            continue
        a = avail.get(name) or {}
        last = periods[-1]
        out.append({
            'name': name,
            'manufacturer': makers.get(name),
            'rsi_id': ids.get(name),
            'avail': a.get('avail'),
            'first_sold_at': ms_to_dt(a.get('firstSold')) or periods[0]['start'],
            'periods': periods,
            'on_sale': any(p['end'] is None for p in periods),
            'warbond_count': sum(1 for p in periods if p['code'] == 'W'),
            'last_price': last['price'],
            'msrp': next((p['msrp'] for p in reversed(periods) if p['msrp'] is not None), None),
        })
    return out
