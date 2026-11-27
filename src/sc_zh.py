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
  - 任務／勢力：英文標題／名稱反查，key 用片段比對（見下方「任務／勢力」一節）。
  - 任務類型（reward_scope）／聲望種類：內部代號直接當 key（RepScope_<代號>_Name、別名表）→ 英文反查
    RepScope_*（聲望範圍名稱）→ mobiGlas_ui_MissionType_* → mobiglas_ui_*。
  - 聲望階級名稱：英文反查 RepStanding_*／RepScope_*_Rank*。
"""

import re
from typing import Optional

from src.models import translation as T
from src.models.translation import DEFAULT_LANG, manual_key


def _manual(domain: str) -> str:
    return manual_key(domain, '')


# ── 載具 ────────────────────────────────────────────────────────────

def vehicle_name_zh(class_name: str = '', name: str = '', lang: str = DEFAULT_LANG,
                    game_name: str = '') -> Optional[str]:
    """載具 class_name（優先）→ 遊戲內英文全名 game_name → 英文名稱 → 翻譯，查不到回傳 None。

    Wiki 的 class_name 跟遊戲 key 不一定一樣（例如 Constellation Mk V Centaurus 在遊戲裡是
    vehicle_NameRSI_Constellation_Mk5_Andromeda），name 又常少了廠商前綴（Constellation Mk V Taurus
    ↔ 遊戲英文 RSI Constellation Mk V Taurus），所以中間用 game_name（遊戲裡的英文全名）反查。
    """
    cls = (class_name or '').strip()
    if cls:
        value = T.by_keys([f'vehicle_Name{cls}_short', f'vehicle_Name{cls}'], lang)
        if value:
            return value
    prefixes = [_manual('vehicle'), 'vehicle_name']
    for text in (game_name, name):
        value = T.by_english(text, prefixes, lang) if text else None
        if value:
            return value
    return None


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


#: 星系本體與其下的星球、衛星、降落點、太空站、Lagrange 點（StantonN／PyroN／NyxN…）。
#: 星球／衛星的說明文字 key（Stanton1_Desc、Pyro3_desc、Stanton2c_Desc,P…）形狀
#: 跟地點 key 一樣，值卻是一整段描述，要用 key 排除掉（不能看值，值就是描述本身）
_KNOWN_LOCATION_KEY = r'^(stanton|pyro|nyx)(\d+[a-z]?(_(?!desc(,p)?$)[a-z0-9]+)?)?$'


def known_location_names(lang: str = DEFAULT_LANG) -> dict:
    """遊戲裡已知的地點名稱 {英文: 翻譯或 None}，給地點下拉選單列出還沒人用過的地點。"""
    return T.by_key_pattern(_KNOWN_LOCATION_KEY, lang)


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

def crafting_slot_zh(name: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """藍圖配方的部位名稱（例如 'Frame'、'Barrel'）→ 翻譯（遊戲 key crafting_ui_slotname_*）。"""
    return T.by_english(name, ['crafting_ui_slotname_'], lang)


def crafting_stat_zh(name: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """品質會影響的屬性名稱（例如 'Impact Force'、'Recoil Smoothness'）→ 翻譯（遊戲 key StatName_GPP_*）。"""
    return T.by_english(name, ['statname_gpp_', 'weapon_stats_name_'], lang)



def blueprint_type_zh(output_type: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """藍圖 output_type 代碼（例如 'WeaponGun'）→ 翻譯（人工條目）。"""
    code = (output_type or '').strip()
    return T.by_key(manual_key('blueprint_type', code), lang) if code else None


def item_type_zh(item_type: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """物品類型代碼（item_master.type，例如 'WeaponPersonal'、'Char_Armor_Torso'）→ 翻譯。

    依序找：人工改名 item_type_override（翻譯包的叫法不好懂時，例如 Shield「護盾生成器」→「護盾」）、
    遊戲 key item_Type<代碼>、item_Type<代碼>,P（遊戲有幾個 key 尾巴多了「,P」，例如
    item_TypeFlightController,P）、人工條目 item_type（遊戲本身不顯示的內部零件類型，翻譯包沒有）、
    藍圖類型的人工條目（代碼是同一套）。"""
    code = (item_type or '').strip()
    if not code:
        return None
    return T.by_keys([manual_key('item_type_override', code), f'item_Type{code}', f'item_Type{code},P',
                      manual_key('item_type', code),
                      manual_key('blueprint_type', code)], lang)


def item_sub_type_zh(sub_type: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """物品子類型代碼（item_master.sub_type，例如 'Sniper'）→ 翻譯（遊戲 key item_SubType<代碼>、
    item_SubType<代碼>,P，翻譯包沒有的用人工條目 item_sub_type）。"""
    code = (sub_type or '').strip()
    if not code or code == 'UNDEFINED':
        return None
    return T.by_keys([f'item_SubType{code}', f'item_SubType{code},P', manual_key('item_sub_type', code)], lang)


def item_class_zh(item_class: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """組件類別（item_master.item_class：Civilian／Industrial／Military／Stealth／Competition）→ 翻譯
    （人工條目 item_class）。"""
    code = (item_class or '').strip()
    return T.by_key(manual_key('item_class', code), lang) if code else None


def blueprint_type_names(lang: str = DEFAULT_LANG) -> dict:
    """全部藍圖類型 {代碼: 翻譯}，給前端一次載入。"""
    return T.manual_domain('blueprint_type', lang)


# ── 廠商 ────────────────────────────────────────────────────────────
#
# 翻譯包以廠商代碼為 key：manufacturer_NameCRUS＝十字軍工業、manufacturer_NameRSI＝羅伯茲太空工業…
# （同一前綴下的 manufacturer_Desc<代碼> 是介紹文字，不收）。

_MFR_PREFIX = 'manufacturer_Name'


def manufacturer_zh(text: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """廠商代碼（CRUS）或英文全名（Crusader Industries）→ 翻譯。"""
    text = (text or '').strip()
    if not text:
        return None
    return T.by_key(f'{_MFR_PREFIX}{text}', lang) or T.by_english(text, [_MFR_PREFIX.lower()], lang)


def manufacturer_names(lang: str = DEFAULT_LANG) -> dict:
    """全部廠商 {代碼（大寫）: 翻譯}，給前端一次載入。"""
    return {code.upper(): zh for code, zh in T.by_key_prefix(_MFR_PREFIX, lang).items()}


# ── 任務／勢力 ──────────────────────────────────────────────────────
#
# 任務、勢力資料來自 Star Citizen Wiki API，沒有附 localization key，只能拿英文
# 去反查。兩者的 key 都沒有共同前綴，所以用 key 片段比對（T.match_english）：
#
#   - 任務標題：`mg_klim_localdelivery_drugprod_title_intro`、
#     `Intersec_TSG_Group_Title_001`、`RAIN_..._name_01`… → 含 title／_name
#   - 任務說明：通常就是把標題 key 的 title 換成 desc
#     （`..._title_intro` → `..._desc_intro`），找到標題 key 才推得出來
#   - 任務發布者（NPC）：`MissionGivers_WallaceKlim`、`WallaceKlim_RepUI_Name`…
#   - 勢力：`Adagio_RepUI_DisplayName`、`Aciedo_RepUI_Name`…；同一個前綴底下還有
#     `_RepUI_Description`／`_Focus`／`_HQ`／`_Leadership`／`_Area`／`_Founded`
#
# 翻譯包會在任務標題後面加自己的標記，例如「需要戰術打擊小組 <EM4>[300 聲望]
# [藍圖]</EM4>」——那是給遊戲內任務清單看的提示，不是標題本身，顯示前拿掉。

_MISSION_TITLE_PATTERNS = [r'^manual\.mission\.', r'title', r'_name']
_MISSION_GIVER_PATTERNS = [r'^manual\.mission_giver\.', r'^missiongivers_',
                           r'_repui_(display)?name$', r'_from$']
_FACTION_NAME_PATTERNS = [r'^manual\.faction\.', r'_repui_displayname$', r'_repui_name$',
                          r'^missiongivers_', r'_faction_\w*title$', r'_from$']

_EM_BLOCK = re.compile(r'\s*<EM\d*>.*?</EM\d*>', re.S | re.I)
_EM_TAG = re.compile(r'</?EM\d*>', re.I)
_OTHER_TAG = re.compile(r'</?[A-Za-z][^>]{0,20}>')
_MISSION_TOKEN = re.compile(r'~mission\(([^)|]*)(?:\|[^)]*)?\)')
_WIKI_TOKEN = re.compile(r'\[([^\]|]+)\|[^\]]*\]')


#: 翻譯包標題裡有、但英文標題常常沒有的代入欄位：沒有值時整個拿掉，不顯示成 [CargoRouteToken]
_OPTIONAL_TOKENS = {'cargoroutetoken'}


def clean_title_zh(value: Optional[str], fills: dict = None) -> Optional[str]:
    """翻譯包任務標題 → 顯示用：拿掉 <EM4>[藍圖]</EM4> 這類附加標記；
    `~mission(Location)` 代入欄位換成 fills 裡對應的值（Wiki 標題已經填好的部分），
    沒有就顯示成 `[Location]`（_OPTIONAL_TOKENS 裡的直接拿掉）。"""
    if not value:
        return value
    fills = {k.lower(): v for k, v in (fills or {}).items()}

    def fill(m):
        name = m.group(1).strip().lower()
        if fills.get(name):
            return fills[name]
        return '' if name in _OPTIONAL_TOKENS else f'[{m.group(1)}]'
    out = _EM_BLOCK.sub('', value)
    out = _MISSION_TOKEN.sub(fill, out)
    out = _OTHER_TAG.sub('', out).replace('\\n', ' ')
    out = re.sub(r'[ \t]{2,}', ' ', out).strip()
    return out or None


#: 樣板代入值的翻譯：Wiki 標題填的是英文（Master、Large、Interstellar），翻譯包有對應的字
_FILL_PREFIXES = {
    'cargogradetoken': ['haulcargo_cargograde_'],
    'cargoroutetoken': ['haulcargo_cargoroute_'],
}


def _zh_fills(fills: dict, lang: str = DEFAULT_LANG) -> dict:
    """樣板比對出來的英文代入值 → 翻譯（聲望等級、貨運規模、航線範圍）；查不到留英文；
    Wiki 沒解析的 `[CargoRouteToken]` 這種值當成沒有。"""
    out = {}
    for name, value in (fills or {}).items():
        v = (value or '').strip()
        if not v or re.fullmatch(r'\[[^\]]*\]', v):
            continue
        key = name.lower()
        if key == 'reputationrank':
            out[name] = rep_rank_zh(v, lang) or v
        elif key in _FILL_PREFIXES:
            out[name] = T.by_english(v, _FILL_PREFIXES[key], lang) or v
        else:
            out[name] = v
    return out


#: Wiki 標題偶爾是兩段英文黏在一起（"Master | [CargoRouteToken] LargeMaster Rank - Large Cargo Haul"）：
#: 小寫字母後面直接接大寫開頭的字、中間沒有空白，就從那裡切開分別比對
_GLUED = re.compile(r'(?<=[a-z\]])(?=[A-Z][a-z])')


def _title_parts(title: str) -> list:
    # 太短的片段（例如 microTech 切出來的 "Tech"）不拿來比，免得對到別的標題
    parts = [p.strip() for p in _GLUED.split(title or '') if len(p.strip()) >= 12]
    return sorted(parts, key=len, reverse=True) if len(parts) > 1 else []


def clean_text_zh(value: Optional[str]) -> Optional[str]:
    """翻譯包的說明文字 → 顯示用：字面上的 \\n 換成換行、拿掉 <EM4> 標籤
    （保留內容）、`~mission(Location|Address)` 這類遊戲代入欄位改成 `[Location]`。"""
    if not value:
        return value
    out = value.replace('\\n', '\n')
    out = _EM_TAG.sub('', out)
    out = _MISSION_TOKEN.sub(lambda m: f'[{m.group(1)}]' if m.group(1) else '', out)
    return out.strip() or None


def clean_mission_text(value: Optional[str]) -> Optional[str]:
    """Wiki API 的任務說明 → 顯示用：`[Pickup1|Address]` → `[Pickup1]`，
    殘留的 `~mission(...)` 與 <EM4> 標籤同上處理。"""
    if not value:
        return value
    out = _WIKI_TOKEN.sub(lambda m: f'[{m.group(1)}]', value)
    out = _EM_TAG.sub('', out)
    out = _MISSION_TOKEN.sub(lambda m: f'[{m.group(1)}]' if m.group(1) else '', out)
    return out.strip() or None


def _text_fingerprint(text: str, size: int = 60) -> str:
    """比對兩段說明是不是同一段用：拿掉代入欄位、標籤、標點空白，只留字母數字。"""
    t = _MISSION_TOKEN.sub(' ', text or '')
    t = re.sub(r'\[[^\]]*\]', ' ', t)
    t = _EM_TAG.sub(' ', t).replace('\\n', ' ')
    return re.sub(r'[^a-z0-9]+', '', t.lower())[:size]


def _desc_keys_for(title_key: str) -> list:
    """任務標題 key → 可能的說明 key（title→desc／description，_name→_desc）。"""
    k = (title_key or '').lower()
    out = []
    if 'title' in k:
        i = k.rfind('title')
        out += [k[:i] + 'desc' + k[i + 5:], k[:i] + 'description' + k[i + 5:]]
    if '_name' in k:
        i = k.rfind('_name')
        out.append(k[:i] + '_desc' + k[i + 5:])
    return [x for x in dict.fromkeys(out) if x != k]


def mission_text_zh(title: str, description: str = '', lang: str = DEFAULT_LANG) -> dict:
    """任務英文標題（＋英文說明）→ `{'title_zh', 'description_zh', 'title_key'}`，
    查不到的欄位是 None。

    同一個英文標題常有好幾個 key（同一系列任務的變體，翻譯可能不一樣），有說明
    時優先挑「推得出說明 key、而且那段英文說明跟這個任務的說明對得上」的那個；
    都對不上就用優先順序最高的標題，說明留 None（寧可不翻也不要配錯段落）。
    """
    out = {'title_zh': None, 'description_zh': None, 'title_key': None}
    # 先找英文相同（或只差代入欄位寫法、引號、空白）的；都沒有才用樣板比對已經填好值的標題
    # （"Delivery for Lorville Ready" ↔ "Delivery for ~mission(Destination) Ready"）
    def find(text):
        found = [(k, v, {}) for k, v in T.candidates_by_english(text, _MISSION_TITLE_PATTERNS, lang)]
        if not found:
            found = T.template_candidates(text, _MISSION_TITLE_PATTERNS, lang)
        return [c for c in found if 'desc' not in c[0]]

    # 黏在一起的兩段英文先分開試（長的先）——整段拿去比樣板會把前一段整個當成代入值；都比不到才用整段
    # （整段英文剛好有一模一樣的條目時照用，例如標題裡本來就有 microTech 這種大小寫）
    candidates = [(k, v, {}) for k, v in T.candidates_by_english(title, _MISSION_TITLE_PATTERNS, lang)
                  if 'desc' not in k]
    for part in ([] if candidates else _title_parts(title)):
        candidates = find(part)
        if candidates:
            break
    if not candidates:
        candidates = find(title)
    candidates = [(k, v, _zh_fills(f, lang)) for k, v, f in candidates]
    if not candidates:
        return out

    want = _text_fingerprint(description) if description else ''
    if want:
        for key, value, fills in candidates:
            for desc_key in _desc_keys_for(key):
                en = T.english_of(desc_key)
                if not en:
                    continue
                got = _text_fingerprint(en)
                n = min(len(got), len(want))
                if n >= 20 and got[:n] == want[:n]:
                    return {'title_zh': clean_title_zh(value, fills),
                            'description_zh': clean_text_zh(T.by_key(desc_key, lang)),
                            'title_key': key}

    key, value, fills = candidates[0]
    return {'title_zh': clean_title_zh(value, fills), 'description_zh': None, 'title_key': key}


#: 任務類型（reward_scope）的查法：上游給的是聲望範圍名稱（RepScope_*_Name，例如 Assassination），
#: 再來是 mobiGlas 合約分類（mobiGlas_ui_MissionType_*、mobiglas_ui_*）；人工條目放最前面，翻譯包沒有的才補
_MISSION_TYPE_PREFIXES = ['repscope_', 'mobiglas_ui_missiontype_', 'mobiglas_ui_']


#: 聲望種類的內部代號（勢力階級表 reputation_ladder 的 scope，例如 FactionReputation、BountyHunter）
#: 跟翻譯包 key 拼法不同的 → 直接指定 key（小寫比對）
_SCOPE_KEY_ALIASES = {
    'factionreputation': ['mobiGlas_Reputation_Standing'],          # 立場
    'bountyhunter': ['RepScope_Bounty_Name'],                       # 賞金獵人
    'bountyhunting': ['RepScope_Bounty_Name'],
    'missiongiver': ['RepScope_MissionGiver_Default_Name'],         # 親和度
    'hauling': ['RepScope_TransportGuild_Name'],                    # 貨運
}


def mission_type_zh(scope: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """任務類型／聲望種類 → 翻譯，查不到回 None。

    上游有兩種寫法：顯示用的英文（reward_scope，例如 Hauling、Assassination）跟內部代號
    （階級表的 scope，例如 FactionReputation、BountyHunter、Security）。依序試：
    人工條目 → 代號直接當 key（別名表、RepScope_<代號>_Name、mobiGlas_Reputation_ScopeTitle_<代號>）
    → 英文反查 RepScope_*／mobiGlas 合約分類。
    """
    text = (scope or '').strip()
    if not text:
        return None
    value = T.by_english(text, [_manual('mission_type')], lang)
    if value:
        return value
    ident = re.sub(r'[^0-9A-Za-z_]', '', text)
    if ident:
        keys = list(_SCOPE_KEY_ALIASES.get(ident.lower(), []))
        keys += [f'RepScope_{ident}_Name', f'RepScope_{ident}_Default_Name',
                 f'mobiGlas_Reputation_ScopeTitle_{ident}']
        value = T.by_keys(keys, lang)
        if value:
            return value
    return T.by_english(text, _MISSION_TYPE_PREFIXES, lang)


#: 聲望階級名稱（例如 Junior Contractor）：英文反查 RepStanding_*（不含 _Perk 說明）／RepScope_*_Rank*
_REP_RANK_PATTERNS = [r'^repstanding_(?!.*_perks?$)', r'^repscope_.*_rank\d']


def rep_rank_zh(name: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """勢力聲望階級名稱 → 翻譯（人工條目優先），查不到回 None。"""
    text = (name or '').strip()
    if not text:
        return None
    value = T.by_english(text, [_manual('rep_rank')], lang)
    if value:
        return value
    hit = T.match_english(text, _REP_RANK_PATTERNS, lang)
    return hit[1] if hit else None


def mission_giver_zh(name: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """任務發布者（NPC 名稱，例如 'Wallace Klim'）→ 翻譯。"""
    hit = T.match_english(name, _MISSION_GIVER_PATTERNS, lang)
    return clean_title_zh(hit[1]) if hit else None


#: 勢力介紹的欄位 → RepUI key 後綴（候選依序試；HQ 有兩種寫法、還有拼錯的）
_FACTION_FIELD_KEYS = {
    'description':  ['description'],
    'focus':        ['focus'],
    'headquarters': ['hq', 'headquarters', 'headquaters'],
    'leadership':   ['leadership'],
    'area':         ['area'],
    'founded':      ['founded'],
}


def faction_texts_zh(name: str, lang: str = DEFAULT_LANG) -> dict:
    """勢力英文名稱 → `{'name_zh', 'description_zh', 'focus_zh', 'headquarters_zh',
    'leadership_zh', 'area_zh', 'founded_zh'}`，查不到的欄位是 None。

    名稱對到 `<前綴>_RepUI_Name`／`_DisplayName` 時，同前綴的其他 RepUI 條目就是
    這個勢力的介紹欄位；對到的是其他類 key（任務發布者、勢力標題…）就只有名稱。
    """
    out = {'name_zh': None, **{f'{f}_zh': None for f in _FACTION_FIELD_KEYS}}
    hit = T.match_english(name, _FACTION_NAME_PATTERNS, lang)
    if not hit:
        return out
    key, value = hit
    out['name_zh'] = clean_title_zh(value)
    i = key.find('_repui_')
    if i > 0:
        prefix = key[:i + len('_repui_')]
        for field, suffixes in _FACTION_FIELD_KEYS.items():
            out[f'{field}_zh'] = clean_text_zh(T.by_keys([prefix + s for s in suffixes], lang))
    return out


def faction_name_zh(name: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """勢力英文名稱 → 翻譯（只要名稱時用，例如任務列表的勢力欄）。"""
    hit = T.match_english(name, _FACTION_NAME_PATTERNS, lang)
    return clean_title_zh(hit[1]) if hit else None


# ── 星圖地點（scunpacked-data starmap.json）────────────────────────────
#
# 星圖的名稱是遊戲解析好的英文，沒有附 key，用英文反查。地點名稱的 key 分散在好幾類
# （StantonN_…、asteroidcluster_miningbase_…、pyro6_outpost_…、miningclaim…、
# ab_mine_…），前面的優先；說明是一整段英文，直接找英文完全相同的那段。
# 設施（Amenities）是 Maps_Amenities_*；管轄是 Jurisdictions_Name_* 或勢力名稱；
# 類型是 Markers_Subtext_<類型>，翻譯包沒有的幾個放人工條目（manual.starmap_type.*）。

_STARMAP_NAME_PATTERNS = [
    r'^manual\.location\.', r'^(stanton|pyro|nyx)', r'^asteroidcluster_', r'^fob_',
    r'^mission_location_', r'^miningclaim', r'^rr_', r'^ab_mine_', r'^gobling', r'^hangar_',
    r'destination', r'^delemar_', r'^ui_dest_', r'^area_name_', r'^station_area_', r'^mission',
    r'^contestedzone', r'^miningasteroidbase', r'^invictus', r'location',
]
_AMENITY_PATTERNS = [r'^maps_amenities_', r'^area_name_', r'^station_area_']
_JURISDICTION_PATTERNS = [r'^jurisdictions_name_', r'_repui_displayname$', r'_repui_name$',
                          r'^factions_\w+_displayname$', r'_from$']


def starmap_name_zh(name: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """星圖地點英文名稱（例如 'Blackrock Exchange'）→ 翻譯。"""
    if not (name or '').strip():
        return None
    hit = T.match_english(name, _STARMAP_NAME_PATTERNS, lang)
    return clean_title_zh(hit[1]) if hit else None


def starmap_description_zh(text: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """星圖地點的英文說明 → 翻譯（找英文完全相同的那一段，說明類 key 優先）。"""
    if not (text or '').strip():
        return None
    hit = T.match_english(text, [r'desc', r'.'], lang)
    return clean_text_zh(hit[1]) if hit else None


def amenity_zh(name: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """地點設施（例如 'Vehicle Services'、'Landing Pad (M)'）→ 翻譯。"""
    hit = T.match_english(name, _AMENITY_PATTERNS, lang) if (name or '').strip() else None
    return clean_title_zh(hit[1]) if hit else None


def jurisdiction_zh(name: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """管轄單位（例如 'UEE'、"People's Alliance"）→ 翻譯。"""
    hit = T.match_english(name, _JURISDICTION_PATTERNS, lang) if (name or '').strip() else None
    return clean_title_zh(hit[1]) if hit else None


def starmap_type_zh(code: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """星圖類型代碼（Planet、Asteroid_ValidQT…）→ 翻譯。底線後面是變體，先找完整代碼、再找基本類型。"""
    code = (code or '').strip()
    if not code:
        return None
    base = code.split('_', 1)[0]
    return T.by_keys([manual_key('starmap_type', code), manual_key('starmap_type', base),
                      f'markers_subtext_{code.lower()}', f'markers_subtext_{base.lower()}'], lang)


def starmap_feature_zh(key: str, amenity_names=(), lang: str = DEFAULT_LANG) -> Optional[str]:
    """地點屬性欄位（has_hangar、shop_weapons…，見 src/models/starmap.py 的 FEATURES）→ 翻譯。

    先找人工條目（starmap_feature），再用第一個對應設施的翻譯；一個屬性對應好幾種尺寸
    （機庫 S～XL）時去掉尺寸括號。
    """
    hit = T.by_keys([manual_key('starmap_feature', key)], lang) if key else None
    if hit or not amenity_names:
        return hit
    zh = amenity_zh(amenity_names[0], lang)
    if zh and len(amenity_names) > 1:
        zh = re.sub(r'\s*[（(][^）)]*[）)]\s*$', '', zh) or zh
    return zh


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
    'item_type':       item_type_zh,
    'item_sub_type':   item_sub_type_zh,
    'item_class':      item_class_zh,
    'faction':         faction_name_zh,
    'mission_giver':   mission_giver_zh,
    'mission_type':    mission_type_zh,
    'rep_rank':        rep_rank_zh,
    'starmap_type':    starmap_type_zh,
    'amenity':         amenity_zh,
    'manufacturer':    manufacturer_zh,
}
