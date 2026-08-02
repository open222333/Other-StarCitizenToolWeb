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
    """模擬 3 頁分頁，記錄每次請求的 URL 與 params。"""

    BASE = 'https://api.star-citizen.wiki/api/items'

    def __init__(self):
        self.pages = {
            self.BASE: {'data': [{'uuid': 'a'}],
                        'links': {'next': self.BASE + '?page=2'},
                        'meta': {'current_page': 1, 'last_page': 3, 'total': 3}},
            self.BASE + '?page=2': {'data': [{'uuid': 'b'}],
                                    'links': {'next': self.BASE + '?page=3'},
                                    'meta': {'current_page': 2, 'last_page': 3, 'total': 3}},
            self.BASE + '?page=3': {'data': [{'uuid': 'c'}],
                                    'links': {'next': None},
                                    'meta': {'current_page': 3, 'last_page': 3, 'total': 3}},
        }
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return _FakeResponse(self.pages[url])


def test_pagination_follows_links_next(monkeypatch):
    monkeypatch.setattr(scdata, 'SCDATA_REQUEST_DELAY', 0)
    client = _FakeClient()

    rows = list(scdata.wiki_rows(client, 'items'))

    assert [r['uuid'] for r in rows] == ['a', 'b', 'c']
    assert len(client.calls) == 3
    # 第一次請求帶 page[size]，之後跟著 links.next 就不再重複帶
    assert client.calls[0][1] == {
        'page[size]': scdata.SCDATA_PAGE_SIZES['items'], 'page[number]': 1}
    assert client.calls[1][1] is None


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
