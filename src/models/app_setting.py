"""後台可直接修改的系統設定（`app_settings` collection，一個設定一筆，_id = 設定名稱）。

- 玩家頁分頁的排列順序（PlayerTabOrder，後台「系統設定」）
- 玩家頁分頁的開放狀態（PlayerTabAccess：開放／預設不顯示／不開放，後台「系統設定」）
- 物品類型分組（ItemTypeGroups：物品類型多選篩選的分段，後台「系統設定」）

UEX Corp API token：後台「資料同步排程」頁可以直接填，不用再改 `.env`
重啟容器。後台填的優先；沒填就退回環境變數 `UEX_API_TOKEN`（舊的設定方式照樣能用）。

token 是機密：API 只回「有沒有設定、來源、末 4 碼」，**不會把完整 token 回給前端**，
也不寫進操作紀錄。
"""

import re
from datetime import datetime

from src import UEX_API_TOKEN
from src.mongo import get_db

UEX_TOKEN_ID = 'uex_api_token'
UEX_TOKEN_MAX = 500


def _col():
    return get_db()['app_settings']


def _mask(token: str) -> str:
    return '••••' + token[-4:] if len(token) > 4 else '••••'


class UexToken:
    """UEX API token：後台設定（DB）優先，其次環境變數。"""

    @staticmethod
    def get() -> str:
        doc = _col().find_one({'_id': UEX_TOKEN_ID}) or {}
        return (doc.get('value') or '').strip() or UEX_API_TOKEN

    @staticmethod
    def status() -> dict:
        doc = _col().find_one({'_id': UEX_TOKEN_ID}) or {}
        value = (doc.get('value') or '').strip()
        if value:
            return {'configured': True, 'source': 'admin', 'masked': _mask(value),
                    'updated_at': doc.get('updated_at'), 'updated_by': doc.get('updated_by')}
        if UEX_API_TOKEN:
            return {'configured': True, 'source': 'env', 'masked': _mask(UEX_API_TOKEN),
                    'updated_at': None, 'updated_by': None}
        return {'configured': False, 'source': None, 'masked': '',
                'updated_at': None, 'updated_by': None}

    @staticmethod
    def set(token, updated_by=None) -> dict:
        """存後台填的 token；空字串＝清掉（改回用環境變數）。格式不對丟 ValueError。"""
        if not isinstance(token, str):
            raise ValueError('token 格式錯誤')
        token = token.strip()
        if len(token) > UEX_TOKEN_MAX or any(c.isspace() for c in token):
            raise ValueError('token 格式錯誤（不能有空白，最多 500 字）')
        if token:
            _col().update_one({'_id': UEX_TOKEN_ID}, {'$set': {
                'value': token, 'updated_at': datetime.utcnow(), 'updated_by': updated_by}},
                upsert=True)
        else:
            _col().delete_one({'_id': UEX_TOKEN_ID})
        return UexToken.status()


PLAYER_TAB_ORDER_ID = 'player_tab_order'
#: 分頁代號的格式（實際有哪些分頁由前端 frontend/src/utils/playerTabs.js 決定，後端只擋格式、數量）。
#: 下層分頁（子功能）寫成「主分頁.下層分頁」，例如 items.data、toolbox.loadout：
#: 順序跟主分頁存在同一個清單裡，開放狀態也在同一個 dict（下層分頁前端只用 open／closed）。
_TAB_KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,19}(\.[a-z][a-z0-9_]{0,19})?$')
TAB_ORDER_MAX = 120


class PlayerTabOrder:
    """玩家頁分頁的排列順序（後台「系統設定」可拖拉排序）。空清單＝照程式預設順序。

    清單裡沒列到的分頁（例如之後新增的）由前端接在最後面，所以這裡存的順序不會擋住新分頁。
    """

    @staticmethod
    def get() -> list:
        doc = _col().find_one({'_id': PLAYER_TAB_ORDER_ID}) or {}
        value = doc.get('value')
        return [k for k in value if isinstance(k, str)] if isinstance(value, list) else []

    @staticmethod
    def set(keys, updated_by=None) -> list:
        """格式不對丟 ValueError；重複的只留第一個。"""
        if not isinstance(keys, list) or len(keys) > TAB_ORDER_MAX \
                or not all(isinstance(k, str) and _TAB_KEY_RE.match(k) for k in keys):
            raise ValueError('分頁順序格式錯誤')
        keys = list(dict.fromkeys(keys))
        _col().update_one({'_id': PLAYER_TAB_ORDER_ID}, {'$set': {
            'value': keys, 'updated_at': datetime.utcnow(), 'updated_by': updated_by}}, upsert=True)
        return keys


PLAYER_TAB_ACCESS_ID = 'player_tab_access'
#: 分頁開放狀態：open＝開放（預設）、hidden＝預設不顯示（玩家可以在「個人資料」自己打開）、closed＝不開放（玩家看不到也打不開）
TAB_ACCESS_VALUES = ('open', 'hidden', 'closed')
#: 一定開放的分頁（玩家要靠它打開其他分頁）
TAB_ALWAYS_OPEN = ('profile',)


class PlayerTabAccess:
    """玩家頁分頁的開放狀態（後台「系統設定」）。只存不是 open 的分頁：{分頁代號: hidden／closed}。"""

    @staticmethod
    def get() -> dict:
        doc = _col().find_one({'_id': PLAYER_TAB_ACCESS_ID}) or {}
        value = doc.get('value')
        if not isinstance(value, dict):
            return {}
        return {k: v for k, v in value.items()
                if isinstance(k, str) and v in TAB_ACCESS_VALUES and v != 'open' and k not in TAB_ALWAYS_OPEN}

    @staticmethod
    def set(access, updated_by=None) -> dict:
        """access：{分頁代號: open／hidden／closed}；格式不對丟 ValueError。open 的不存。"""
        if not isinstance(access, dict) or len(access) > TAB_ORDER_MAX:
            raise ValueError('分頁開放狀態格式錯誤')
        clean = {}
        for k, v in access.items():
            if not (isinstance(k, str) and _TAB_KEY_RE.match(k)) or v not in TAB_ACCESS_VALUES:
                raise ValueError('分頁開放狀態格式錯誤')
            if v != 'open' and k not in TAB_ALWAYS_OPEN:
                clean[k] = v
        _col().update_one({'_id': PLAYER_TAB_ACCESS_ID}, {'$set': {
            'value': clean, 'updated_at': datetime.utcnow(), 'updated_by': updated_by}}, upsert=True)
        return clean


ITEM_TYPE_GROUPS_ID = 'item_type_groups'
#: 物品類型代碼（item_master.type）／前綴的格式
_ITEM_TYPE_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
ITEM_GROUPS_MAX = 30
ITEM_GROUP_TYPES_MAX = 300
ITEM_GROUP_PREFIXES_MAX = 10
ITEM_GROUP_LABEL_MAX = 20
#: 預設分組（沒存過、或「恢復預設」時用）。types＝完整代碼，prefixes＝代碼前綴（例如 Char_Armor_ 涵蓋各部位護甲）
DEFAULT_ITEM_TYPE_GROUPS = [
    {'label': '艦船組件', 'types': ['QuantumDrive', 'Shield', 'Radar', 'Cooler', 'PowerPlant', 'JumpDrive',
                                'QuantumInterdictionGenerator', 'LifeSupportGenerator', 'EMP', 'ExternalFuelTank'],
     'prefixes': []},
    {'label': '艦船武器', 'types': ['WeaponGun', 'Missile', 'MissileLauncher', 'Bomb', 'BombLauncher',
                                'GroundVehicleMissileLauncher', 'WeaponDefensive', 'Turret', 'TurretBase'],
     'prefixes': []},
    {'label': '採礦／打撈／牽引', 'types': ['WeaponMining', 'MiningModifier', 'SalvageHead', 'SalvageModifier',
                                     'TractorBeam', 'TowingBeam'], 'prefixes': []},
    {'label': '個人武器', 'types': ['WeaponPersonal', 'WeaponAttachment', 'Grenade'], 'prefixes': []},
    {'label': '個人護甲', 'types': ['Suit'], 'prefixes': ['Char_Armor_']},
    {'label': '服飾', 'types': [], 'prefixes': ['Char_Clothing_', 'Char_Accessory_']},
    {'label': '消耗品', 'types': ['Food', 'Drink', 'Bottle', 'FPS_Consumable'], 'prefixes': []},
    {'label': '塗裝／裝飾', 'types': ['Paints'], 'prefixes': ['Flair_']},
]


def _codes(value, limit: int, what: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit \
            or not all(isinstance(v, str) and _ITEM_TYPE_RE.match(v) for v in value):
        raise ValueError(f'{what}格式錯誤')
    return list(dict.fromkeys(value))


class ItemTypeGroups:
    """物品類型分組：多選篩選（frontend MultiSelectFilter）依群組分段、可整組勾選。
    沒對到任何群組的類型由前端歸「其他」；同一個類型只能在一個群組（前綴重疊時排前面的群組優先）。"""

    @staticmethod
    def get() -> dict:
        doc = _col().find_one({'_id': ITEM_TYPE_GROUPS_ID}) or {}
        value = doc.get('value')
        if not isinstance(value, list):
            return {'groups': [dict(g) for g in DEFAULT_ITEM_TYPE_GROUPS], 'custom': False}
        groups = [{'label': g.get('label'), 'types': list(g.get('types') or []), 'prefixes': list(g.get('prefixes') or [])}
                  for g in value if isinstance(g, dict) and isinstance(g.get('label'), str)]
        return {'groups': groups, 'custom': True}

    @staticmethod
    def set(groups, updated_by=None) -> dict:
        """groups：[{label, types, prefixes}]；None／空陣列＝恢復預設。格式不對丟 ValueError。"""
        if not groups:
            _col().delete_one({'_id': ITEM_TYPE_GROUPS_ID})
            return ItemTypeGroups.get()
        if not isinstance(groups, list) or len(groups) > ITEM_GROUPS_MAX:
            raise ValueError(f'分組最多 {ITEM_GROUPS_MAX} 個')
        clean, labels, owner = [], set(), {}
        for i, g in enumerate(groups, start=1):
            if not isinstance(g, dict):
                raise ValueError('分組格式錯誤')
            label = g.get('label').strip() if isinstance(g.get('label'), str) else ''
            if not label or len(label) > ITEM_GROUP_LABEL_MAX:
                raise ValueError(f'第 {i} 組：名稱要 1～{ITEM_GROUP_LABEL_MAX} 個字')
            if label in labels or label == '其他':
                raise ValueError(f'第 {i} 組：名稱「{label}」重複')
            labels.add(label)
            types = _codes(g.get('types'), ITEM_GROUP_TYPES_MAX, f'{label}：類型')
            for t in types:
                if t in owner:
                    raise ValueError(f'類型 {t} 同時在「{owner[t]}」和「{label}」')
                owner[t] = label
            prefixes = _codes(g.get('prefixes'), ITEM_GROUP_PREFIXES_MAX, f'{label}：前綴')
            clean.append({'label': label, 'types': types, 'prefixes': prefixes})
        _col().update_one({'_id': ITEM_TYPE_GROUPS_ID}, {'$set': {
            'value': clean, 'updated_at': datetime.utcnow(), 'updated_by': updated_by}}, upsert=True)
        return {'groups': clean, 'custom': True}
