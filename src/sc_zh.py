"""全站中文化的領域查詢（載具、物品、地點、礦物、藍圖類型…）。

翻譯本身一律存在資料庫（collection `sc_translations`，見
src/models/translation.py），由同步排程從遊戲英文表（scunpacked-data
labels.json）＋社群繁中化包（cosmo-chang-1701/sc-translation-pack）寫入；
翻譯包沒有、人工補的條目在 src/data/sc_translation_manual.json，同步時一併
寫入。這裡只負責「某種東西要用哪個遊戲 key／哪一類英文去查」，不再維護任何
對照表 —— 需要中文化的新地方，請在這裡加一個查詢函式，不要另外做 JSON 表。

每個函式都有 `lang` 參數（預設 zh-TW），之後加語言不用改呼叫端的邏輯。
查不到一律回 None，呼叫端顯示英文。

各類查法：
  - 載具名稱：vehicle_Name<class_name>_short → vehicle_Name<class_name>（_short
    不含廠商名，跟 vehicle_master.name 的寫法一致），再退回用英文名稱反查。
  - 載具角色：用英文角色反查 vehicle_class_*／vehicle_focus_*；上游 role 字串跟
    翻譯包 key 拼法不同的幾個（refueling／refuelling、gunship／gunshio…）走別名。
  - 物品：item_Name<class_name>，再退回英文名稱反查 item_name*。
  - 地點：英文名稱反查 Stanton*／Pyro*／Nyx*。
  - 礦物：英文名稱（含去掉 (Ore)／(Raw)／(Pure)／(R) 後綴、去掉 "Raw " 前綴的
    寫法）反查 items_commodities_*。
  - 礦床：人工條目（岩石／小行星分類）→ 同礦物的查法。
  - 藍圖類型：人工條目（遊戲 output_type 代碼，翻譯包沒有）。
"""

import re
from typing import Optional

from src.models import translation as T
from src.models.translation import DEFAULT_LANG, manual_key


def _manual(domain: str) -> str:
    return manual_key(domain, '')


# ── 載具 ────────────────────────────────────────────────────────────

def vehicle_name_zh(class_name: str = '', name: str = '', lang: str = DEFAULT_LANG) -> Optional[str]:
    """載具 class_name（優先）或英文名稱 → 翻譯，查不到回傳 None。"""
    cls = (class_name or '').strip()
    if cls:
        value = T.by_keys([f'vehicle_Name{cls}_short', f'vehicle_Name{cls}'], lang)
        if value:
            return value
    return T.by_english(name, [_manual('vehicle'), 'vehicle_name'], lang)


#: 上游 role 字串 → 翻譯包 key（英文對不上、但翻譯包確實有同義條目的）
_ROLE_KEY_ALIASES = {
    'starterlightmining':   'vehicle_class_startermining',
    'starterlightsalvage':  'vehicle_class_startersalvage',
    'heavyrefueling':       'vehicle_class_heavyrefuelling',       # 翻譯包拼成 refuelling
    'mediumfreightgunship': 'vehicle_class_mediumfreightgunshio',  # 翻譯包拼錯成 gunshio
    'cargo':                'vehicle_class_cargo_loader',
    'combat':               'vehicle_focus_combat',
    'transport':            'vehicle_focus_transporter',
}


def _role_norm(role: str) -> str:
    return ''.join(ch for ch in (role or '').lower() if ch.isalnum())


def vehicle_role_zh(role: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """載具角色（例如 'Heavy Fighter'）→ 翻譯，查不到回傳 None。"""
    role = (role or '').strip()
    if not role:
        return None
    value = T.by_english(role, [_manual('vehicle_role'), 'vehicle_class_', 'vehicle_focus_'], lang)
    if value:
        return value
    norm = _role_norm(role)
    keys = [k for k in (_ROLE_KEY_ALIASES.get(norm), f'vehicle_class_{norm}') if k]
    return T.by_keys(keys, lang)


# ── 物品 ────────────────────────────────────────────────────────────

def item_name_zh(en_name: str = '', class_name: str = '', lang: str = DEFAULT_LANG) -> Optional[str]:
    """物品 class_name（優先）或英文名稱 → 翻譯，查不到回傳 None。"""
    cls = (class_name or '').strip()
    if cls:
        value = T.by_key(f'item_Name{cls}', lang)
        if value:
            return value
    return T.by_english(en_name, [_manual('item'), 'item_name'], lang)


# ── 地點 ────────────────────────────────────────────────────────────

#: 地點名稱會出現在好幾類 key 底下：星系本體（StantonN_…）、小行星帶採礦基地、
#: 廢棄前哨站、任務地點…；前面的優先
_LOCATION_PREFIXES = ['stanton', 'pyro', 'nyx', 'asteroidcluster_', 'fob_', 'mission_location_']


def location_name_zh(en_name: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """地點英文名稱 → 翻譯，查不到回傳 None。"""
    return T.by_english(en_name, [_manual('location')] + _LOCATION_PREFIXES, lang)


#: 星系本體與其下的星球、衛星、降落點、太空站、Lagrange 點（StantonN／PyroN／NyxN…），
#: 不含 _Desc 之類的說明文字 key
_KNOWN_LOCATION_KEY = r'^(stanton|pyro|nyx)(\d+[a-z]?(_[a-z0-9]+)?)?$'


def known_location_names(lang: str = DEFAULT_LANG) -> dict:
    """遊戲裡已知的地點名稱 {英文: 翻譯或 None}，給地點下拉選單列出還沒人用過的地點。"""
    return {en: zh for en, zh in T.by_key_pattern(_KNOWN_LOCATION_KEY, lang).items()
            if not en.lower().endswith(' desc')}


# ── 礦物／礦床 ──────────────────────────────────────────────────────

_MINERAL_SUFFIX = re.compile(r'\s*\((ore|raw|pure|r)\)\s*$', re.I)


def _mineral_variants(name: str) -> list:
    """礦物名稱的查詢候選：原名優先（翻譯包對原礦有自己的譯名，例如
    「綠柱石（原礦）」），查不到才試去掉 (Ore)／(Raw)／(Pure)／(R) 後綴、
    去掉 "Raw " 前綴的精煉品名稱。"""
    name = (name or '').strip()
    if not name:
        return []
    out = [name]
    bare = _MINERAL_SUFFIX.sub('', name).strip()
    if bare and bare not in out:
        out.append(bare)
    for v in list(out):
        if v.lower().startswith('raw '):
            stripped = v[4:].strip()
            if stripped and stripped not in out:
                out.append(stripped)
    return out


def mining_resource_name_zh(resource_key: str = '', name: str = '',
                            lang: str = DEFAULT_LANG) -> Optional[str]:
    """礦物（例如 'Hephaestanite (R)'、resource_key 'Raw_Hephaestanite'）→ 翻譯。

    以英文名稱查；沒給名稱時用 resource_key 還原（'Raw_Ice' → 'Raw Ice'）。
    """
    candidates = _mineral_variants(name) or _mineral_variants((resource_key or '').replace('_', ' '))
    for text in candidates:
        value = T.by_english(text, [_manual('mining_resource'), 'items_commodities_'], lang)
        if value:
            return value
    return None


def mining_deposit_name_zh(deposit_name: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """礦床名稱（例如 'Granite Deposit'、'Aluminum (Ore)'）→ 翻譯。

    岩石／小行星分類是人工條目；單一礦物的礦床直接用礦物名稱當礦床名，
    所以其他情況用礦物的查法。
    """
    value = T.by_english(deposit_name, [_manual('mining_deposit')], lang)
    return value or mining_resource_name_zh(name=deposit_name, lang=lang)


# ── 藍圖 ────────────────────────────────────────────────────────────

def blueprint_type_zh(output_type: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """藍圖 output_type 代碼（例如 'WeaponGun'）→ 翻譯（人工條目）。"""
    code = (output_type or '').strip()
    return T.by_key(manual_key('blueprint_type', code), lang) if code else None


def blueprint_type_names(lang: str = DEFAULT_LANG) -> dict:
    """全部藍圖類型 {代碼: 翻譯}，給前端一次載入。"""
    return T.manual_domain('blueprint_type', lang)


# ── 給 API 用的批次查詢 ──────────────────────────────────────────────

#: domain → 單筆查詢函式（英文文字 → 翻譯），給 /item/translations 批次查
LOOKUPS = {
    'location':        location_name_zh,
    'item':            lambda text, lang=DEFAULT_LANG: item_name_zh(text, lang=lang),
    'vehicle':         lambda text, lang=DEFAULT_LANG: vehicle_name_zh(name=text, lang=lang),
    'vehicle_role':    vehicle_role_zh,
    'mining_resource': lambda text, lang=DEFAULT_LANG: mining_resource_name_zh(name=text, lang=lang),
    'mining_deposit':  mining_deposit_name_zh,
    'blueprint_type':  blueprint_type_zh,
}
