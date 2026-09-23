"""遊戲資料抓取與欄位映射測試（src/scdata.py）。

用真實 API 回應片段驗證，不需要網路。
片段抓取於 2026-08，Star Citizen Wiki API，遊戲版本 4.9.0-LIVE。
"""
import pytest

from src import scdata

# ─────────────────────────────────────────── 真實回應片段

ITEM = {
    'uuid': '7b21462f-b0ad-433e-9809-d1a97f9e511e',
    'slug': '100i-2954-auspicious-red-dog-livery',
    'name': '100i 2954 Auspicious Red Dog Livery',
    'class_name': 'Paint_100i_LunarNewYears2954_Red_Gold_Dog',
    'classification': 'Ship.Paints',
    'description': {'en_EN': 'Seek peace and prosperity...', 'zh_CN': '新的一年...'},
    'size': 1, 'mass': 0, 'grade': 'A',
    'is_base_variant': False, 'is_craftable': False, 'is_lootable': False,
    'manufacturer': {'name': 'Origin Jumpworks', 'code': 'ORIG'},
    'type': 'Paints', 'sub_type': 'UNDEFINED',
    'dimension': {
        'width': 0.75, 'height': 0.75, 'length': 0.75,
        'volume': 0.024, 'volume_converted': 24000, 'volume_converted_unit': 'µSCU',
        'cargo_dimension': {'width': 0.3, 'height': 0.2, 'length': 0.4},
    },
    'tags': ['Paint_100i'],
    'uex_prices': {'purchase': []},
    'web_url': 'https://api.star-citizen.wiki/items/100i-2954-auspicious-red-dog-livery',
    'updated_at': '2026-07-17T08:08:23.000000Z',
    'version': '4.9.0-LIVE.12232306',
}

VEHICLE = {
    'uuid': '97648869-5fa5-42da-b804-4d9314289539',
    'name': 'Avenger Stalker', 'game_name': 'Aegis Avenger Stalker',
    'slug': 'aegs-avenger-stalker', 'class_name': 'AEGS_Avenger_Stalker',
    'mass': 48986, 'mass_hull': 48986,
    'cargo_capacity': 0, 'ore_capacity': None, 'cargo_grids': [],
    'vehicle_inventory': 710000,
    'inventory_containers': [{'width': 2, 'height': 2, 'length': 2,
                              'volume': 8, 'scu': 0.71, 'closed': True}],
    'crew': {'min': 1, 'max': 1},
    'manufacturer': {'name': 'Aegis Dynamics', 'code': 'AEGS'},
    'size_class': 2, 'is_spaceship': True, 'is_gravlev': False,
    'career': 'Combat', 'role': 'Interceptor', 'msrp': 60,
    'updated_at': '2026-06-28T00:36:52.000000Z',
    'version': '4.8.2-LIVE.12030094',
}

COMMODITY = {
    'uuid': 'dc6fbcbb-5990-4ed5-82ee-93152dab7845',
    'key': 'Agricium', 'name': 'Agricium', 'display_name': 'Agricium (Metal)',
    'slug': 'agricium', 'density_g_per_cc': 1, 'tier': None,
    'box_sizes_scu': [0.125, 1, 2, 4, 8, 16, 24, 32],
    'is_mineable': False, 'has_salvage': False,
    'commodity_groups': ['Metal'],
}


# ─────────────────────────────────────────── 映射

def test_map_item():
    doc = scdata.map_item(ITEM)
    assert doc['_id'] == ITEM['uuid']
    assert doc['class_name'] == 'Paint_100i_LunarNewYears2954_Red_Gold_Dog'
    assert doc['name_lower'] == '100i 2954 auspicious red dog livery'
    assert doc['manufacturer_code'] == 'ORIG'
    assert doc['volume_uscu'] == 24000          # µSCU，不是 SCU
    assert doc['volume_unit'] == 'µSCU'
    assert doc['cargo_dimension']['width'] == 0.3
    assert doc['description_en'].startswith('Seek peace')
    assert doc['game_version'] == '4.9.0-LIVE.12232306'
    assert doc['raw'] is ITEM, '原始回應要完整保留，加欄位才不必重抓 API'


def test_map_vehicle_unit_distinction():
    doc = scdata.map_vehicle(VEHICLE)
    assert doc['_id'] == VEHICLE['uuid']
    # cargo_capacity 是 SCU，vehicle_inventory 是 µSCU —— 兩者單位不同
    assert doc['cargo_capacity_scu'] == 0
    assert doc['vehicle_inventory_uscu'] == 710000
    assert scdata.uscu_to_scu(doc['vehicle_inventory_uscu']) == 0.71
    assert doc['crew_max'] == 1
    assert doc['manufacturer_code'] == 'AEGS'
    assert doc['name_lower'] == 'avenger stalker'


def test_map_commodity():
    doc = scdata.map_commodity(COMMODITY)
    assert doc['_id'] == COMMODITY['uuid']
    assert doc['key'] == 'Agricium'
    assert doc['box_sizes_scu'][0] == 0.125
    assert doc['commodity_groups'] == ['Metal']


def test_mappers_reject_missing_uuid():
    assert scdata.map_item({'name': 'no uuid'}) is None
    assert scdata.map_vehicle({}) is None
    assert scdata.map_commodity({'key': 'x'}) is None


def test_uscu_conversion():
    assert scdata.uscu_to_scu(1_000_000) == 1.0
    assert scdata.uscu_to_scu(24_000) == 0.024
    assert scdata.uscu_to_scu(None) == 0


# ─────────────────────────────────────────── 分頁

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.headers = {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    """模擬分頁：每次請求都打同一個 URL，靠 params 裡的 page[number] 決定
    回傳第幾頁的資料——跟新版 wiki_rows() 的實際行為一致（不再解析
    links，完全靠自己算頁碼 + 上游回報的 meta.current_page 前進）。
    """

    BASE = 'https://api.star-citizen.wiki/api/items'

    def __init__(self, pages=None):
        # {page_number: {'data': [...], 'meta': {...}}}
        self.pages = pages or {
            1: {'data': [{'uuid': 'a'}], 'meta': {'current_page': 1, 'last_page': 3, 'total': 3}},
            2: {'data': [{'uuid': 'b'}], 'meta': {'current_page': 2, 'last_page': 3, 'total': 3}},
            3: {'data': [{'uuid': 'c'}], 'meta': {'current_page': 3, 'last_page': 3, 'total': 3}},
        }
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        page = (params or {}).get('page[number]', 1)
        return _FakeResponse(self.pages[page])


def test_pagination_walks_pages_via_meta_current_page(monkeypatch):
    monkeypatch.setattr(scdata, 'SCDATA_REQUEST_DELAY', 0)
    client = _FakeClient()

    rows = list(scdata.wiki_rows(client, 'items'))

    assert [r['uuid'] for r in rows] == ['a', 'b', 'c']
    assert len(client.calls) == 3
    # 每次都是同一個 URL，用乾淨的 page[number] 換頁，不解析/不依賴 links
    assert {url for url, _ in client.calls} == {client.BASE}
    assert [params['page[number]'] for _, params in client.calls] == [1, 2, 3]
    assert client.calls[0][1]['page[size]'] == scdata.SCDATA_PAGE_SIZES['items']


def test_pagination_ignores_upstream_duplicate_key_link_bug(monkeypatch):
    """實測踩到的真實上游 bug：blueprints 這種帶 include 的大分頁，從某頁
    開始上游回應的 links（不只 next，所有分頁連結）會把「這次請求用的
    page[number]」跟「目標頁碼」一起留在 URL 裡，變成帶重複 key 的畸形
    連結；照著打，上游用第一個 key（舊頁碼），回傳的還是同一頁，永遠
    前進不了，形成真正的無窮迴圈。

    新版完全不解析 links 欄位（這裡故意塞一個會製造無窮迴圈的 links.next
    進假資料，藉此驗證它真的被忽略），只靠 meta.current_page 自己算下一頁，
    天生不會被這個上游 bug 影響。
    """
    monkeypatch.setattr(scdata, 'SCDATA_REQUEST_DELAY', 0)
    pages = {
        1: {'data': [{'uuid': 'a'}], 'meta': {'current_page': 1, 'last_page': 3, 'total': 3},
            'links': {'next': _FakeClient.BASE + '?page[number]=1&page[number]=1'}},
        2: {'data': [{'uuid': 'b'}], 'meta': {'current_page': 2, 'last_page': 3, 'total': 3},
            'links': {'next': _FakeClient.BASE + '?page[number]=2&page[number]=2'}},
        3: {'data': [{'uuid': 'c'}], 'meta': {'current_page': 3, 'last_page': 3, 'total': 3},
            'links': {'next': _FakeClient.BASE + '?page[number]=3&page[number]=3'}},
    }
    client = _FakeClient(pages)

    rows = list(scdata.wiki_rows(client, 'items'))

    assert [r['uuid'] for r in rows] == ['a', 'b', 'c']
    assert len(client.calls) == 3


def test_pagination_stops_at_max_pages_when_current_page_stuck(monkeypatch):
    """安全網：萬一 meta.current_page 真的卡住不前進（比目前實測到的上游
    bug 更壞的情況），WIKI_PAGINATION_MAX_PAGES 要能強制停止，不會真的
    無窮迴圈。"""
    monkeypatch.setattr(scdata, 'SCDATA_REQUEST_DELAY', 0)
    monkeypatch.setattr(scdata, 'WIKI_PAGINATION_MAX_PAGES', 5)

    class _StuckClient:
        BASE = 'https://api.star-citizen.wiki/api/items'

        def __init__(self):
            self.calls = []

        def get(self, url, params=None):
            self.calls.append((url, dict(params or {})))
            # 不管要求第幾頁，永遠回報還在第 1 頁——模擬 current_page 卡死
            return _FakeResponse({'data': [{'uuid': 'x'}],
                                   'meta': {'current_page': 1, 'last_page': 99, 'total': 99}})

    client = _StuckClient()
    rows = list(scdata.wiki_rows(client, 'items'))

    assert len(client.calls) == 5
    assert len(rows) == 5


def test_uex_doc_id():
    assert scdata.uex_doc_id({'id': 42}, ['id']) == '42'
    assert scdata.uex_doc_id({'id_item': 7, 'id_terminal': 149},
                             ['id_item', 'id_terminal']) == '7:149'
    # 缺任一欄位就回 None，不要組出半截主鍵
    assert scdata.uex_doc_id({'id_item': 7}, ['id_item', 'id_terminal']) is None
    assert scdata.uex_doc_id({'id': None}, ['id']) is None


def test_uex_rows_rejects_error_status():
    class _ErrClient:
        def get(self, url, params=None):
            return _FakeResponse({'status': 'requests_limit_reached', 'data': []})

    with pytest.raises(scdata.ScDataError, match='requests_limit_reached'):
        scdata.uex_rows(_ErrClient(), 'items')


def test_resource_maps_are_consistent():
    """WIKI_RESOURCES 的 mapper 都要能處理空 dict 而不爆炸。"""
    for resource, (collection, mapper) in scdata.WIKI_RESOURCES.items():
        assert collection.endswith('_master'), resource
        assert mapper({}) is None, resource


# ─────────────────────────────────────────── scunpacked-data（礦物回波參考表）
#
# 片段取自 StarCitizenWiki/scunpacked-data 的 resources/resources.json 與
# resources/locations.json（2026-09 快照）。

MINING_DEPOSIT = {
    'UUID': '3e9ecb49-dee6-433d-b7d4-cef0dbf31931',
    'Key': 'GPI_Icicle',
    'Name': '<= PLACEHOLDER =>',
    'Kind': 'mineable',
    'GlobalParams': {'PowerCapacityPerMass': 5, 'DecayPerMass': 0.2},
    'Composition': {
        'UUID': '51922796-a927-46dc-bf09-57deac090fa1',
        'DepositName': 'Granite Deposit',
        'MinimumDistinctElements': 2,
        'Parts': [
            {'UUID': '3776294d-5689-41f2-b03d-e8fcd17ede6a',
             'ResourceTypeUUID': 'e30bdd32-8fd5-44b8-9994-5fd253a16c37',
             'Key': 'Ore_Aluminum', 'Name': 'Aluminum (Ore)',
             'MinPercentage': 30, 'MaxPercentage': 70, 'Probability': 1},
            {'UUID': 'f2f5bf2e-87f9-4f3d-bb59-b4e11eceeaad',
             'ResourceTypeUUID': '57aba429-cf97-4fdd-8042-94b1d643f5bd',
             'Key': 'Ore_Gold', 'Name': 'Gold (Ore)',
             'MinPercentage': 20, 'MaxPercentage': 50, 'Probability': 0.3},
        ],
    },
    'Tier': 'common',
    'Signature': 4000,
}

MINING_LOCATION = {
    'Provider': {'UUID': 'adbddd5e-c6fb-49bd-bd93-750cb54efd08',
                 'Name': 'HPP_ShipGraveyard_001', 'PresetFile': 'hpp_shipgraveyard_001'},
    'Locations': [
        {'Key': None, 'System': 'Stanton', 'Name': 'Ship Graveyard', 'Type': 'unknown'},
    ],
    'Areas': [],
    'Groups': [
        {'GroupName': 'Salvage_FreshDerelicts', 'GroupProbability': 0.04,
         'Deposits': [
             {'ResourceUUID': '3e9ecb49-dee6-433d-b7d4-cef0dbf31931',
              'RelativeProbability': 0.9922822491730982},
         ]},
    ],
}


def test_map_mining_deposit(seed_translations):
    # 中文查 sc_translations：礦物是翻譯包條目，"Granite Deposit" 是人工條目
    # （翻譯包沒有，標準地質學術語，見 src/data/sc_translation_manual.json）
    seed_translations({
        'items_commodities_aluminum_ore': ('Aluminum (Ore)', '鋁礦石'),
        'items_commodities_gold_ore': ('Gold (Ore)', '金礦石'),
    })
    doc = scdata.map_mining_deposit(MINING_DEPOSIT)
    assert doc['_id'] == MINING_DEPOSIT['UUID']
    assert doc['deposit_name'] == 'Granite Deposit'
    assert doc['deposit_name_lower'] == 'granite deposit'
    # "Granite Deposit" 翻譯包沒有對應資料，是標準地質學術語（非猜測）：花崗岩礦床
    assert doc['deposit_name_zh'] == '花崗岩礦床'
    assert doc['tier'] == 'common'
    assert doc['min_distinct_elements'] == 2
    assert doc['signature'] == 4000
    assert len(doc['parts']) == 2
    aluminum = doc['parts'][0]
    assert aluminum == {
        'resource_key': 'Ore_Aluminum', 'resource_name': 'Aluminum (Ore)',
        'resource_name_zh': '鋁礦石',
        'min_percentage': 30, 'max_percentage': 70, 'probability': 1,
    }
    # 查不到對照表的 key 要回 None，不能讓整筆同步掛掉
    gold = doc['parts'][1]
    assert gold['resource_key'] == 'Ore_Gold'
    assert gold['resource_name_zh'] == '金礦石'
    assert doc['raw'] is MINING_DEPOSIT


def test_map_mining_deposit_skips_non_mineable_and_empty_composition():
    # 資源集裡 Kind 還有 cave_harvestable / salvageable / harvestable，
    # 這個表只收 mineable（礦物回波用得到成分機率的只有這種）。
    non_mineable = dict(MINING_DEPOSIT, Kind='cave_harvestable')
    assert scdata.map_mining_deposit(non_mineable) is None

    no_uuid = dict(MINING_DEPOSIT)
    no_uuid.pop('UUID')
    assert scdata.map_mining_deposit(no_uuid) is None

    no_parts = dict(MINING_DEPOSIT, Composition={'DepositName': 'Empty', 'Parts': []})
    assert scdata.map_mining_deposit(no_parts) is None


def test_map_mining_location():
    doc = scdata.map_mining_location(MINING_LOCATION)
    assert doc['_id'] == MINING_LOCATION['Provider']['UUID']
    assert doc['provider_name'] == 'HPP_ShipGraveyard_001'
    assert doc['system'] == 'Stanton'
    assert doc['location_name'] == 'Ship Graveyard'
    assert doc['location_name_lower'] == 'ship graveyard'
    # "Ship Graveyard" 翻譯包沒有這個獨立詞條（只在別的長句子裡出現過），
    # 查不到要回 None，不能讓整筆同步掛掉，前端會退回顯示英文。
    assert doc['location_name_zh'] is None
    assert len(doc['groups']) == 1
    group = doc['groups'][0]
    assert group['group_name'] == 'Salvage_FreshDerelicts'
    assert group['deposits'] == [{
        'resource_uuid': '3e9ecb49-dee6-433d-b7d4-cef0dbf31931',
        'relative_probability': 0.9922822491730982,
    }]
    assert doc['raw'] is MINING_LOCATION


def test_map_mining_location_skips_missing_provider_uuid_or_empty_groups():
    no_uuid = {'Provider': {'Name': 'x'}, 'Locations': [], 'Groups': [{'Deposits': [{'ResourceUUID': 'a'}]}]}
    assert scdata.map_mining_location(no_uuid) is None

    no_groups = {'Provider': {'UUID': 'u1'}, 'Locations': [], 'Groups': []}
    assert scdata.map_mining_location(no_groups) is None

    # Deposits 裡每筆都缺 ResourceUUID → 整個 group 沒有可用礦床 → 整筆跳過
    empty_deposits = {'Provider': {'UUID': 'u1'}, 'Locations': [],
                       'Groups': [{'GroupName': 'g', 'Deposits': [{'RelativeProbability': 1}]}]}
    assert scdata.map_mining_location(empty_deposits) is None


def test_scunpacked_resource_maps_are_consistent():
    """SCUNPACKED_RESOURCES 的 mapper 都要能處理空 dict 而不爆炸。"""
    for resource, (collection, path, mapper) in scdata.SCUNPACKED_RESOURCES.items():
        assert collection.endswith('_master'), resource
        assert path, resource
        assert mapper({}) is None, resource
