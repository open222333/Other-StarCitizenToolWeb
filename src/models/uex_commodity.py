"""UEX 商品（`uex_commodities`，UEX Corp API 的 /commodities）與礦物的關聯。

UEX 的商品有一個 4 碼左右的縮寫 `code`（例如 AGRI、QUAN、TARA），交易／價格網站
都用它。礦物資料庫（礦床成分 parts[].resource_key）本身沒有這個代碼，這裡用英文名稱
自動對應：

  1. 先比完全同名（不分大小寫），例如 Carinite (Pure) ↔ Carinite (Pure)
  2. 找不到才把 (Ore)／(Raw)／(Pure)／(R) 後綴、"Raw " 前綴拿掉再比
     （規則跟 frontend/src/utils/miningSignature.js 的 mineralBaseName 一致）
  3. 同一個名稱 UEX 常有精煉品與原礦（is_raw）兩筆：主要代碼取非原礦那筆，
     原礦代碼另外放 raw_code

名稱寫法差太多對不起來的，後台礦物資料庫可以手動指定（`mineral_uex_links`，
_id = resource_key），手動的優先；指定成「不關聯」也是一種手動設定。
"""

import re
from datetime import datetime
from typing import Optional

from src.mongo import get_db

COLLECTION = 'uex_commodities'
LINKS = 'mineral_uex_links'

_SUFFIX = re.compile(r'\s*\((ore|raw|pure|r)\)\s*$', re.IGNORECASE)
_RAW_PREFIX = re.compile(r'^raw\s+', re.IGNORECASE)

_FIELDS = {'id': 1, 'code': 1, 'name': 1, 'kind': 1, 'is_raw': 1, 'is_refined': 1, 'is_mineral': 1}


def _lower(text) -> str:
    return (text or '').strip().lower() if isinstance(text, str) else ''


def base_name(text) -> str:
    return _RAW_PREFIX.sub('', _SUFFIX.sub('', _lower(text))).strip()


def _summary(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return {'id': str(doc.get('id', doc.get('_id'))), 'code': doc.get('code') or None,
            'name': doc.get('name'), 'kind': doc.get('kind'), 'is_raw': bool(doc.get('is_raw'))}


class UexCommodity:

    @staticmethod
    def list_all() -> list:
        """全部 UEX 商品摘要（給後台手動指定的下拉選單），依代碼排序。"""
        rows = get_db()[COLLECTION].find({}, _FIELDS)
        out = [_summary(r) for r in rows]
        return sorted(out, key=lambda r: ((r['code'] or '~').upper(), r['name'] or ''))

    #: 後台「商品資料庫」頁列出的欄位（UEX /commodities 的原始欄位，缺的就是 None）
    DETAIL_FIELDS = ('code', 'name', 'kind', 'weight_scu', 'price_buy', 'price_sell',
                     'is_raw', 'is_refined', 'is_mineral', 'is_harvestable', 'is_buyable', 'is_sellable',
                     'is_illegal', 'is_volatile_qt', 'is_volatile_time', 'is_explosive', 'is_available',
                     'date_modified')

    @classmethod
    def list_detail(cls) -> list:
        """後台「商品資料庫」：全部 UEX 商品（約兩三百筆，不分頁），每筆附上關聯到的礦物。"""
        from src.models.mining import MiningDeposit   # 避免循環 import（mining 也 import 這裡）

        minerals = {}
        for dep in get_db()[MiningDeposit.COLLECTION].find({'is_current': True}, {'parts': 1}):
            for part in dep.get('parts') or []:
                if part.get('resource_key') and part['resource_key'] not in minerals:
                    minerals[part['resource_key']] = part
        links = cls.links_for({k: p.get('resource_name') for k, p in minerals.items()})
        by_commodity: dict = {}
        for key, link in links.items():
            part = minerals[key]
            entry = {'resource_key': key, 'resource_name': part.get('resource_name'),
                     'resource_name_zh': part.get('resource_name_zh'), 'source': link.get('source')}
            if link.get('id'):
                by_commodity.setdefault(link['id'], []).append(entry)
            if link.get('raw_id'):
                by_commodity.setdefault(link['raw_id'], []).append({**entry, 'as_raw': True})

        rows = []
        for doc in get_db()[COLLECTION].find({}, {f: 1 for f in ('id',) + cls.DETAIL_FIELDS}):
            row = {f: doc.get(f) for f in cls.DETAIL_FIELDS}
            row['id'] = str(doc.get('id', doc['_id']))
            row['minerals'] = by_commodity.get(row['id'], [])
            rows.append(row)
        return sorted(rows, key=lambda r: ((r['code'] or '~').upper(), r['name'] or ''))

    @staticmethod
    def _pick(candidates: list) -> tuple:
        """(主要那筆, 原礦那筆)：主要取非原礦，原礦另外列。"""
        main = next((c for c in candidates if not c.get('is_raw')), None) or (candidates[0] if candidates else None)
        raw = next((c for c in candidates if c.get('is_raw') and c is not main), None)
        return main, raw

    @classmethod
    def links_for(cls, minerals: dict) -> dict:
        """{resource_key: resource_name} → {resource_key: 關聯}。

        關聯：{id, code, name, raw_code, source: 'auto'|'manual'}；對不到（或手動設成
        不關聯）的是 {code: None, source: ...}。UEX 還沒同步過時全部是 None。
        """
        db = get_db()
        commodities = [c for c in db[COLLECTION].find({}, _FIELDS) if c.get('name')]
        by_id = {str(c.get('id', c['_id'])): c for c in commodities}
        exact, base = {}, {}
        for c in commodities:
            exact.setdefault(_lower(c['name']), []).append(c)
            base.setdefault(base_name(c['name']), []).append(c)
        manual = {d['_id']: d for d in db[LINKS].find({'_id': {'$in': list(minerals)}})} if minerals else {}

        out = {}
        for key, name in minerals.items():
            if key in manual:
                doc = by_id.get(str(manual[key].get('uex_id'))) if manual[key].get('uex_id') else None
                main = _summary(doc)
                out[key] = {**(main or {'code': None}), 'raw_code': None, 'raw_id': None, 'source': 'manual'}
                continue
            candidates = exact.get(_lower(name)) or base.get(base_name(name)) or []
            main, raw = cls._pick(candidates)
            if main is None:
                out[key] = {'code': None, 'raw_code': None, 'raw_id': None, 'source': 'auto'}
                continue
            raw_code = (raw or {}).get('code')
            out[key] = {**_summary(main), 'raw_code': raw_code if raw_code != main.get('code') else None,
                        'raw_id': _summary(raw)['id'] if raw else None, 'source': 'auto'}
        return out

    @staticmethod
    def set_link(resource_key: str, uex_id, updated_by=None) -> None:
        """手動指定礦物對應的 UEX 商品。

        uex_id：UEX 商品 id（字串／數字）＝ 指定；'' ＝ 指定成不關聯；None ＝ 清掉手動設定、
        改回自動比對。id 不存在丟 ValueError。
        """
        col = get_db()[LINKS]
        if uex_id is None:
            col.delete_one({'_id': resource_key})
            return
        uex_id = str(uex_id).strip()
        if uex_id and not get_db()[COLLECTION].find_one({'_id': uex_id}, {'_id': 1}):
            raise ValueError('找不到這個 UEX 商品')
        col.update_one({'_id': resource_key}, {'$set': {
            'uex_id': uex_id or None, 'updated_at': datetime.utcnow(), 'updated_by': updated_by}},
            upsert=True)
