"""庫存 / 主檔 API 端點測試（app/inventory、app/item）。

重點在 HTTP 層：認證、權限、參數驗證、回應格式。
庫存邏輯本身在 test_inventory.py 測。
"""
import pytest

from src import WMS_SCOPE_ID
from src.models.inventory import Inventory
from src.mongo import get_db

ITEM_BIG = {'_id': 'item-big', 'name': 'Agricium', 'name_lower': 'agricium',
            'type': 'Commodity', 'volume_uscu': 1_000_000, 'is_current': True,
            'size': 1, 'manufacturer_code': 'ORIG'}
ITEM_SMALL = {'_id': 'item-small', 'name': 'Bracer Cooler', 'name_lower': 'bracer cooler',
              'type': 'Cooler', 'volume_uscu': 24_000, 'is_current': True, 'size': 1}
SHIP = {'_id': 'ship-1', 'name': 'Freelancer MAX', 'name_lower': 'freelancer max',
        'cargo_capacity_scu': 120, 'vehicle_inventory_uscu': 710_000, 'is_current': True}


@pytest.fixture
def seed_master():
    get_db()['item_master'].insert_many([dict(ITEM_BIG), dict(ITEM_SMALL)])
    get_db()['vehicle_master'].insert_one(dict(SHIP))


@pytest.fixture
def viewer_token(client, seed_admin):
    """建一個 viewer 帳號並取得 token，用來驗證寫入權限被擋。"""
    from src.models.user import User
    from src.models.user_template import UserTemplate
    tid = UserTemplate.ensure_defaults()
    User.create('viewer1', 'Viewer1234!', role='viewer', template_id=tid)
    resp = client.post('/auth/login', json={'username': 'viewer1',
                                            'password': 'Viewer1234!'})
    return resp.get_json()['token']


# ─────────────────────────────────────────────────────── 認證

def test_endpoints_require_jwt(client):
    for method, path in [('get', '/inventory/'), ('get', '/item/'),
                         ('post', '/inventory/add'), ('get', '/inventory/capacity')]:
        resp = getattr(client, method)(path, json={})
        assert resp.status_code == 401, f'{method.upper()} {path} 應該要求 JWT'


# ─────────────────────────────────────────────────────── 權限

def test_write_requires_operator_role(client, viewer_token, seed_master):
    resp = client.post('/inventory/add',
                       headers={'Authorization': f'Bearer {viewer_token}'},
                       json={'item': 'item-big', 'quantity': 5, 'location': 'Area18'})
    assert resp.status_code == 403
    assert get_db()['inventory'].count_documents({}) == 0, '被拒的請求不該寫入'


def test_read_allowed_for_viewer(client, viewer_token):
    resp = client.get('/inventory/',
                      headers={'Authorization': f'Bearer {viewer_token}'})
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


# ─────────────────────────────────────────────────────── 列表：多選 / 關鍵字 / 排序
# （庫存管理列表：全站搜尋優化計畫第 4 項。模型層邏輯在 test_inventory.py 測，
#  這裡只驗證 view 有沒有把 query string 正確轉成模型參數。）

def test_list_multiple_location_is_multi_select(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
               json={'item': 'item-big', 'quantity': 5, 'location': 'Area18'})
    client.post('/inventory/add', headers=auth_headers,
               json={'item': 'item-big', 'quantity': 3, 'location': 'Lorville'})
    client.post('/inventory/add', headers=auth_headers,
               json={'item': 'item-big', 'quantity': 1, 'location': 'Orison'})

    resp = client.get('/inventory/?location=Area18&location=Lorville', headers=auth_headers)
    body = resp.get_json()
    assert body['total'] == 2
    assert {r['location'] for r in body['data']} == {'Area18', 'Lorville'}
    # summary 也要跟著篩選條件變，不能列表被篩過但總量還是全庫的數字
    assert body['summary']['total_scu'] == 8.0


def test_list_container_keyword(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
               json={'item': 'item-big', 'quantity': 5, 'location': 'Area18',
                     'container': 'Cargo Box A'})
    client.post('/inventory/add', headers=auth_headers,
               json={'item': 'item-small', 'quantity': 5, 'location': 'Area18',
                     'container': 'Storage Crate'})

    resp = client.get('/inventory/?container=cargo', headers=auth_headers)
    body = resp.get_json()
    assert body['total'] == 1
    assert body['data'][0]['container'] == 'Cargo Box A'


def test_list_name_keyword_query(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
               json={'item': 'item-big', 'quantity': 5, 'location': 'Area18'})
    client.post('/inventory/add', headers=auth_headers,
               json={'item': 'item-small', 'quantity': 5, 'location': 'Area18'})

    resp = client.get('/inventory/?q=agric', headers=auth_headers)
    body = resp.get_json()
    assert body['total'] == 1
    assert body['data'][0]['item_name'] == 'Agricium'


def test_list_sort_by_quantity_desc(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
               json={'item': 'item-big', 'quantity': 2, 'location': 'Area18'})
    client.post('/inventory/add', headers=auth_headers,
               json={'item': 'item-small', 'quantity': 50, 'location': 'Area18'})

    resp = client.get('/inventory/?sort_by=quantity&sort_dir=desc', headers=auth_headers)
    rows = resp.get_json()['data']
    assert [r['quantity'] for r in rows] == [50, 2]


# ─────────────────────────────────────────────────────── 入出庫


def test_add_then_list(client, auth_headers, seed_master):
    resp = client.post('/inventory/add', headers=auth_headers,
                       json={'item': 'item-big', 'quantity': 10,
                             'location': 'Area18', 'note': '首批'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['quantity'] == 10
    assert data['item_name'] == 'Agricium'
    assert data['total_scu'] == 10.0

    resp = client.get('/inventory/?location=Area18', headers=auth_headers)
    body = resp.get_json()
    assert body['total'] == 1
    assert body['data'][0]['item_name'] == 'Agricium'
    assert body['summary']['total_scu'] == 10.0


def test_add_accepts_item_name(client, auth_headers, seed_master):
    """item 欄位可以給名稱，不一定要 uuid。"""
    resp = client.post('/inventory/add', headers=auth_headers,
                       json={'item': 'agricium', 'quantity': 3, 'location': 'Area18'})
    assert resp.status_code == 200
    assert resp.get_json()['data']['item_id'] == 'item-big'


def test_add_unknown_item_400(client, auth_headers, seed_master):
    resp = client.post('/inventory/add', headers=auth_headers,
                       json={'item': '不存在的物品', 'quantity': 1, 'location': 'Area18'})
    assert resp.status_code == 400
    assert '找不到物品' in resp.get_json()['message']


@pytest.mark.parametrize('payload,reason', [
    ({'item': 'item-big', 'quantity': 0, 'location': 'A'}, '數量 0'),
    ({'item': 'item-big', 'quantity': -5, 'location': 'A'}, '負數'),
    ({'item': 'item-big', 'quantity': 'abc', 'location': 'A'}, '非整數'),
    ({'item': 'item-big', 'quantity': 5}, '缺 location'),
    ({'quantity': 5, 'location': 'A'}, '缺 item'),
])
def test_add_validation(client, auth_headers, seed_master, payload, reason):
    resp = client.post('/inventory/add', headers=auth_headers, json=payload)
    assert resp.status_code == 400, reason


def test_remove_insufficient_400(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 5, 'location': 'Area18'})

    resp = client.post('/inventory/remove', headers=auth_headers,
                       json={'item': 'item-big', 'quantity': 99, 'location': 'Area18'})
    assert resp.status_code == 400
    assert '庫存不足' in resp.get_json()['message']

    doc = get_db()['inventory'].find_one({'item_id': 'item-big'})
    assert doc['quantity'] == 5, '失敗的出庫不該改動庫存'


def test_remove_to_zero_flags_emptied(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 4, 'location': 'Area18'})
    resp = client.post('/inventory/remove', headers=auth_headers,
                       json={'item': 'item-big', 'quantity': 4, 'location': 'Area18'})
    assert resp.get_json()['data']['emptied'] is True


def test_move(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 20, 'location': 'Area18'})

    resp = client.post('/inventory/move', headers=auth_headers,
                       json={'item': 'item-big', 'quantity': 8,
                             'source': 'Area18', 'destination': 'Lorville',
                             'destination_container': 'Hangar 3'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['source']['remaining'] == 12
    assert data['destination']['quantity'] == 8
    assert data['destination']['container'] == 'Hangar 3'


def test_writes_are_audited(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 6, 'location': 'Area18'})

    # inventory_log（庫存稽核）
    resp = client.get('/inventory/history', headers=auth_headers)
    rows = resp.get_json()['data']
    assert len(rows) == 1
    assert rows[0]['action'] == 'add'
    assert rows[0]['item_name'] == 'Agricium'
    assert rows[0]['actor_id'].startswith('web:')

    # logs（系統操作紀錄）也要有一筆
    assert get_db()['logs'].count_documents({'action': 'inventory_add'}) == 1


# ─────────────────────────────────────────────────────── 個人庫

def test_player_scope_requires_player_param(client, auth_headers):
    resp = client.get('/inventory/?owner_type=player', headers=auth_headers)
    assert resp.status_code == 400
    assert 'player' in resp.get_json()['message']


def test_guild_and_player_isolated(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 10, 'location': 'Area18'})
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 7, 'location': 'Area18',
                      'owner_type': 'player', 'player': 'TomLi'})

    guild = client.get('/inventory/', headers=auth_headers).get_json()
    player = client.get('/inventory/?owner_type=player&player=TomLi',
                        headers=auth_headers).get_json()
    assert guild['summary']['units'] == 10
    assert player['summary']['units'] == 7


# ─────────────────────────────────────────────────────── capacity

def test_capacity_with_ship_fits(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 50, 'location': 'Area18'})

    resp = client.get('/inventory/capacity?location=Area18&ship=ship-1',
                      headers=auth_headers)
    ship = resp.get_json()['ship']
    assert ship['name'] == 'Freelancer MAX'
    assert ship['needed_scu'] == 50.0
    assert ship['fits'] is True
    assert ship['remaining_scu'] == 70.0


def test_capacity_with_ship_too_small(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 300, 'location': 'Area18'})

    ship = client.get('/inventory/capacity?ship=Freelancer MAX',
                      headers=auth_headers).get_json()['ship']
    assert ship['fits'] is False
    assert ship['trips'] == 3      # 300 SCU / 120 SCU 貨艙
    assert ship['remaining_scu'] == 0


def test_capacity_unknown_ship_reports_error_not_500(client, auth_headers):
    payload = client.get('/inventory/capacity?ship=不存在的船',
                         headers=auth_headers).get_json()
    assert payload['success'] is True
    assert 'error' in payload['ship']


# ─────────────────────────────────────────────────────── where

def test_where_spans_owners(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 10, 'location': 'Area18'})
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 5, 'location': 'Lorville',
                      'owner_type': 'player', 'player': 'TomLi'})

    body = client.get('/inventory/where/item-big', headers=auth_headers).get_json()
    assert body['summary']['total_quantity'] == 15
    assert body['summary']['total_scu'] == 15.0
    assert {row['owner_type'] for row in body['data']} == {'guild', 'player'}


def test_where_unknown_item_404(client, auth_headers):
    assert client.get('/inventory/where/nope', headers=auth_headers).status_code == 404


def test_where_enriches_holder_display_names(client, auth_headers, seed_master):
    """個人庫的列要帶上暱稱／player_name，前端才顯示得出「暱稱（遊戲ID）」。

    inventory.player 只存 RSI handle，沒有暱稱 —— 這是 where_item 在
    view 層用 Player.display_names_by_scid 批次補上的。
    """
    from src.models.player import Player
    Player.create(player_name='Tom Li', star_citizen_id='TomLi', nickname='湯姆')

    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 5, 'location': 'Lorville',
                      'owner_type': 'player', 'player': 'TomLi'})

    rows = client.get('/inventory/where/item-big', headers=auth_headers).get_json()['data']
    row = next(r for r in rows if r['owner_type'] == 'player')
    assert row['player'] == 'TomLi'
    assert row['nickname'] == '湯姆'
    assert row['player_name'] == 'Tom Li'


def test_where_holder_without_player_record(client, auth_headers, seed_master):
    """名冊裡查不到的 handle（舊資料／已軟刪除）不能讓這支 500。"""
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 3, 'location': 'Area18',
                      'owner_type': 'player', 'player': 'GhostPilot'})

    resp = client.get('/inventory/where/item-big', headers=auth_headers)
    assert resp.status_code == 200
    row = next(r for r in resp.get_json()['data'] if r['owner_type'] == 'player')
    assert row['nickname'] == '' and row['player_name'] == ''


def test_where_guild_rows_have_no_holder_name(client, auth_headers, seed_master):
    """公會庫沒有 player，補名稱的那段不能把它弄壞。"""
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 10, 'location': 'Area18'})

    rows = client.get('/inventory/where/item-big', headers=auth_headers).get_json()['data']
    row = next(r for r in rows if r['owner_type'] == 'guild')
    assert row['nickname'] == '' and row['player_name'] == ''


def test_display_names_by_scid_excludes_secrets(client):
    """這支的回傳會給別人看，不能夾帶 password_hash / notes。"""
    from src.models.player import Player
    Player.create(player_name='Tom Li', star_citizen_id='TomLi', nickname='湯姆',
                  notes='私人備註')
    Player.set_password(Player.find_by_star_citizen_id('TomLi')['_id'], 'secret123')

    out = Player.display_names_by_scid(['TomLi', 'NotThere', '', None])
    assert set(out) == {'TomLi'}
    # 只有顯示名稱與（遮蔽過的）聯絡方式，沒有 password / notes / 公開旗標
    assert set(out['TomLi']) == {'nickname', 'player_name', 'discord_name', 'discord_id'}
    assert '私人備註' not in str(out)


def test_display_names_by_scid_skips_deleted(client):
    """軟刪除的玩家不該出現在給別人看的清單裡。"""
    from src.models.player import Player
    pid = Player.create(player_name='Gone', star_citizen_id='GonePlayer', nickname='走了')
    Player.soft_delete(pid)
    assert Player.display_names_by_scid(['GonePlayer']) == {}


# ─────────────────────────────────────────────── /inventory/search

@pytest.fixture
def seed_search(client, auth_headers, seed_master):
    """兩位玩家 + 公會庫，散在兩個地點，讓四種搜尋都有東西可命中。"""
    from src.models.player import Player
    Player.create(player_name='Tom Li', star_citizen_id='TomLi', nickname='湯姆')
    Player.create(player_name='Alice A', star_citizen_id='AlicePilot', nickname='愛麗絲')

    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 100, 'location': 'Area18'})
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 40, 'location': 'Area18',
                      'owner_type': 'player', 'player': 'TomLi'})
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-small', 'quantity': 7, 'location': 'Lorville',
                      'owner_type': 'player', 'player': 'AlicePilot'})


def _search(client, auth_headers, q):
    resp = client.get(f'/inventory/search?q={q}', headers=auth_headers)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def test_search_requires_q(client, auth_headers):
    assert client.get('/inventory/search', headers=auth_headers).status_code == 400
    assert client.get('/inventory/search?q=%20', headers=auth_headers).status_code == 400


def test_search_by_item_name(client, auth_headers, seed_search):
    """打物品名稱（ITEM_BIG 的 name 是 Agricium，uuid 才是 item-big）。"""
    body = _search(client, auth_headers, 'Agricium')
    assert body['matched']['items'] == 1
    assert {r['item_id'] for r in body['data']} == {'item-big'}
    # 同一個物品的公會庫與個人庫都要出現
    assert {r['owner_type'] for r in body['data']} == {'guild', 'player'}
    assert body['data'][0]['item_name'] == 'Agricium'


def test_search_by_item_name_is_case_insensitive(client, auth_headers, seed_search):
    assert _search(client, auth_headers, 'agri')['matched']['items'] == 1
    assert _search(client, auth_headers, 'AGRI')['matched']['items'] == 1


def test_search_does_not_match_uuid(client, auth_headers, seed_search):
    """uuid 不是給人打的，比對它只會讓奇怪的字串意外命中。"""
    assert _search(client, auth_headers, 'item-big')['matched']['items'] == 0


def test_search_by_location(client, auth_headers, seed_search):
    body = _search(client, auth_headers, 'Lorville')
    assert body['matched']['locations'] == 1
    assert {r['location'] for r in body['data']} == {'Lorville'}


def test_search_by_player_nickname(client, auth_headers, seed_search):
    """打暱稱要看到那個人有什麼 —— inventory 裡存的是遊戲ID，不是暱稱。"""
    body = _search(client, auth_headers, '愛麗絲')
    assert body['matched']['players'] == 1
    assert [r['player'] for r in body['data']] == ['AlicePilot']
    assert body['data'][0]['nickname'] == '愛麗絲'


def test_search_by_star_citizen_id(client, auth_headers, seed_search):
    body = _search(client, auth_headers, 'TomLi')
    assert body['matched']['players'] == 1
    assert {r['player'] for r in body['data']} == {'TomLi'}


def test_search_is_union_not_intersection(client, auth_headers, seed_search):
    """「Area18」同時是地點；命中地點就該回那裡的全部，不需要物品也符合。"""
    body = _search(client, auth_headers, 'Area18')
    assert body['matched']['locations'] == 1
    assert body['matched']['items'] == 0
    assert len(body['data']) == 2          # 公會庫 100 + 湯姆 40


def test_search_no_match_returns_empty_not_everything(client, auth_headers, seed_search):
    """三組都沒解析到時必須回空，不能因為 $or 空掉就變成撈全部。"""
    body = _search(client, auth_headers, 'zzz-nothing-matches')
    assert body['data'] == []
    assert body['matched'] == {'items': 0, 'players': 0, 'locations': 0}


def test_search_any_with_no_criteria_returns_empty(client, seed_search):
    """直接呼叫模型層也要守住同一條規則。"""
    assert Inventory.search_any(WMS_SCOPE_ID) == []
    assert Inventory.search_any(WMS_SCOPE_ID, item_ids=[], players=[], locations=[]) == []


def test_search_escapes_regex(client, auth_headers, seed_search):
    """使用者輸入的 regex 特殊字元不該被當語法，也不該 500。"""
    body = _search(client, auth_headers, '.%2A')      # ".*"
    assert body['data'] == []


def test_search_excludes_zero_quantity(client, auth_headers, seed_search):
    """取到 0 的列不該出現在別人的查詢結果裡。"""
    client.post('/inventory/remove', headers=auth_headers,
                json={'item': 'item-small', 'quantity': 7, 'location': 'Lorville',
                      'owner_type': 'player', 'player': 'AlicePilot'})
    body = _search(client, auth_headers, 'Lorville')
    assert body['data'] == []


def test_search_by_location_chinese_name(client, auth_headers, seed_search, seed_translations):
    """地點中文存在 sc_translations、不在庫存資料上，所以中文搜尋要靠 view 層比對。"""
    seed_translations({'Stanton1_Lorville': ('Lorville', '羅威爾')})
    body = _search(client, auth_headers, '羅威爾')
    assert {r['location'] for r in body['data']} == {'Lorville'}


# ── 分欄位搜尋（item_id／item_type／location／player_id，AND 交集）──
#
# 「查詢 › 物品庫存」拆分欄位自動完成版：跟上面 q（OR 取聯集）是不同語意，
# 見 search_stock() 與 Inventory.search_filtered() 各自的說明。

def _search_filtered(client, auth_headers, **params):
    from urllib.parse import urlencode
    resp = client.get(f'/inventory/search?{urlencode(params)}', headers=auth_headers)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def test_search_filtered_by_item_id(client, auth_headers, seed_search):
    body = _search_filtered(client, auth_headers, item_id='item-big')
    assert {r['item_id'] for r in body['data']} == {'item-big'}
    assert {r['owner_type'] for r in body['data']} == {'guild', 'player'}
    assert body['matched'] is None


def test_search_filtered_by_item_type(client, auth_headers, seed_search):
    """item-small 的 type 是 Cooler，item-big 是 Commodity —— 只篩得到 item-small。"""
    body = _search_filtered(client, auth_headers, item_type='Cooler')
    assert {r['item_id'] for r in body['data']} == {'item-small'}


def test_search_filtered_item_type_no_match_returns_empty(client, auth_headers, seed_search):
    body = _search_filtered(client, auth_headers, item_type='NoSuchType')
    assert body['data'] == []


def test_search_filtered_item_id_takes_precedence_over_item_type(client, auth_headers, seed_search):
    """兩個都給的話用 item_id——item_type='Cooler' 篩不到 item-big，
    但 item_id 已經是精確值，不該再被 item_type 限縮掉。"""
    body = _search_filtered(client, auth_headers, item_id='item-big', item_type='Cooler')
    assert {r['item_id'] for r in body['data']} == {'item-big'}


def test_search_filtered_by_location(client, auth_headers, seed_search):
    body = _search_filtered(client, auth_headers, location='Lorville')
    assert {r['location'] for r in body['data']} == {'Lorville'}


def test_search_filtered_by_player_id(client, auth_headers, seed_search):
    body = _search_filtered(client, auth_headers, player_id='TomLi')
    assert {r['player'] for r in body['data']} == {'TomLi'}
    assert {r['item_id'] for r in body['data']} == {'item-big'}


def test_search_filtered_is_and_not_or(client, auth_headers, seed_search):
    """item_type='Commodity'（只有 item-big）AND location='Lorville'（只有 item-small）
    ——兩個條件同時成立的交集是空的，不能因為任一個有命中就回東西。"""
    body = _search_filtered(client, auth_headers, item_type='Commodity', location='Lorville')
    assert body['data'] == []


def test_search_filtered_narrows_with_multiple_conditions(client, auth_headers, seed_search):
    """item_type='Commodity'（item-big，公會庫 100 + TomLi 40）AND player_id='TomLi'
    ——同時成立的只剩 TomLi 那一筆。"""
    body = _search_filtered(client, auth_headers, item_type='Commodity', player_id='TomLi')
    assert len(body['data']) == 1
    assert body['data'][0]['player'] == 'TomLi'
    assert body['data'][0]['item_id'] == 'item-big'


def test_search_filtered_ignores_q_when_present(client, auth_headers, seed_search):
    """新版參數存在時走 AND 模式，q 被忽略，不會混用兩種語意。"""
    body = _search_filtered(client, auth_headers, item_id='item-big', q='zzz-nothing-matches')
    assert {r['item_id'] for r in body['data']} == {'item-big'}


def test_search_filtered_with_no_criteria_returns_empty_at_model_layer(client, seed_search):
    """直接呼叫模型層：什麼條件都沒給要回空，不能被誤判成撈全部。"""
    assert Inventory.search_filtered(WMS_SCOPE_ID) == []


def test_search_filtered_multiple_item_types_are_ored(client, auth_headers, seed_search):
    """「物品類型」可多選：Cooler（item-small）＋Commodity（item-big）兩種都要。"""
    from urllib.parse import urlencode
    qs = urlencode([('item_type', 'Cooler'), ('item_type', 'Commodity')])
    body = client.get(f'/inventory/search?{qs}', headers=auth_headers).get_json()
    assert {r['item_id'] for r in body['data']} == {'item-small', 'item-big'}


def test_search_filtered_multiple_locations_are_ored(client, auth_headers, seed_search):
    from urllib.parse import urlencode
    qs = urlencode([('location', 'Lorville'), ('location', 'Area18')])
    body = client.get(f'/inventory/search?{qs}', headers=auth_headers).get_json()
    assert {r['location'] for r in body['data']} == {'Lorville', 'Area18'}
    # 多選之間是 OR，跟其他條件仍是 AND：Commodity 只在 Area18
    qs = urlencode([('location', 'Lorville'), ('location', 'Area18'), ('item_type', 'Commodity')])
    body = client.get(f'/inventory/search?{qs}', headers=auth_headers).get_json()
    assert {r['location'] for r in body['data']} == {'Area18'}


def test_search_filtered_item_ids_empty_list_means_no_match(client, seed_search):
    """item_ids 傳空陣列（篩了但沒有物品符合）要跟『沒有篩物品』區分開。"""
    assert Inventory.search_filtered(WMS_SCOPE_ID, item_ids=[]) == []


# ── Discord 公開勾選（discord_public）─────────────────────────
#
# 這組測試守的是隱私不變式：沒勾公開的人，Discord 絕不能出現在
# 「給別人看的清單」裡。預設值必須是不公開。

def test_discord_hidden_by_default(client, auth_headers, seed_master):
    """沒勾公開（也包含舊資料根本沒這個欄位）→ Discord 一律空字串。"""
    from src.models.player import Player
    Player.create(player_name='Tom Li', star_citizen_id='TomLi', nickname='湯姆',
                  discord_name='tomli#1234', discord_id='998877665544')

    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 5, 'location': 'Area18',
                      'owner_type': 'player', 'player': 'TomLi'})

    rows = client.get('/inventory/where/item-big', headers=auth_headers).get_json()['data']
    row = next(r for r in rows if r['owner_type'] == 'player')
    assert row['discord_name'] == '' and row['discord_id'] == ''
    # 連旗標本身都不該回傳
    assert 'discord_public' not in row


def test_discord_shown_when_public(client, auth_headers, seed_master):
    from src.models.player import Player
    Player.create(player_name='Tom Li', star_citizen_id='TomLi', nickname='湯姆',
                  discord_name='tomli#1234', discord_id='998877665544',
                  discord_public=True)

    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 5, 'location': 'Area18',
                      'owner_type': 'player', 'player': 'TomLi'})

    rows = client.get('/inventory/where/item-big', headers=auth_headers).get_json()['data']
    row = next(r for r in rows if r['owner_type'] == 'player')
    assert row['discord_name'] == 'tomli#1234'
    assert row['discord_id'] == '998877665544'


def test_discord_hidden_in_stock_search_too(client, auth_headers, seed_master):
    """/inventory/search 走同一支 display_names_by_scid，也不能漏。"""
    from src.models.player import Player
    Player.create(player_name='Tom Li', star_citizen_id='TomLi', nickname='湯姆',
                  discord_name='tomli#1234', discord_id='9988')
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 5, 'location': 'Area18',
                      'owner_type': 'player', 'player': 'TomLi'})

    body = client.get('/inventory/search?q=Agricium', headers=auth_headers).get_json()
    serialised = str(body)
    assert 'tomli#1234' not in serialised
    assert '9988' not in serialised


def test_player_can_toggle_discord_public(client, seed_master):
    """本人可以自己開關，且值要存成真正的布林而不是字串。"""
    from src.models.player import Player
    Player.create(player_name='Tom Li', star_citizen_id='TomLi', nickname='湯姆',
                  discord_name='tomli#1234', password='pw-123456')
    token = client.post('/player/login', json={
        'star_citizen_id': 'TomLi', 'password': 'pw-123456'}).get_json()['token']
    headers = {'Authorization': f'Bearer {token}'}

    assert client.get('/player/me', headers=headers).get_json()['data'].get('discord_public') in (False, None)

    assert client.put('/player/me', headers=headers,
                      json={'discord_public': True}).status_code == 200
    doc = get_db()['players'].find_one({'star_citizen_id': 'TomLi'})
    assert doc['discord_public'] is True, '必須是布林 True，不是字串'

    assert client.put('/player/me', headers=headers,
                      json={'discord_public': False}).status_code == 200
    doc = get_db()['players'].find_one({'star_citizen_id': 'TomLi'})
    assert doc['discord_public'] is False, '關掉後必須是布林 False'


def test_updating_other_fields_does_not_reset_discord_public(client, seed_master):
    """只改暱稱時不該把公開設定重設 —— partial update 的老問題。"""
    from src.models.player import Player
    Player.create(player_name='Tom Li', star_citizen_id='TomLi', nickname='湯姆',
                  discord_public=True, password='pw-123456')
    token = client.post('/player/login', json={
        'star_citizen_id': 'TomLi', 'password': 'pw-123456'}).get_json()['token']
    headers = {'Authorization': f'Bearer {token}'}

    client.put('/player/me', headers=headers, json={'nickname': '新暱稱'})
    doc = get_db()['players'].find_one({'star_citizen_id': 'TomLi'})
    assert doc['nickname'] == '新暱稱'
    assert doc['discord_public'] is True


# ── 軟刪除的玩家不能再用手上的 token ────────────────────────────
#
# JWT 簽出去就撤不回來（access 8 小時、refresh 30 天）。只看 claim 不查 DB 的話，
# 管理員「移除成員」對個人庫存子系統完全無效。

@pytest.fixture
def deleted_player_headers(client, seed_master):
    """註冊 → 登入拿 token → 把帳號軟刪除，回傳 (headers, refresh_headers)。"""
    from src.models.player import Player
    client.post('/player/register', json={
        'nickname': '要被踢的', 'star_citizen_id': 'Ghost', 'password': 'pw-123456'})
    login = client.post('/player/login', json={
        'star_citizen_id': 'Ghost', 'password': 'pw-123456'}).get_json()

    pid = Player.find_by_star_citizen_id('Ghost')['_id']
    Player.soft_delete(pid)

    return ({'Authorization': f"Bearer {login['token']}"},
            {'Authorization': f"Bearer {login['refresh_token']}"})


def test_soft_deleted_player_cannot_use_inventory(client, deleted_player_headers):
    headers, _ = deleted_player_headers
    for method, path, payload in [
        ('get',  '/player/inventory',         None),
        ('get',  '/player/inventory/history', None),
        ('post', '/player/inventory/add',     {'item': 'item-big', 'quantity': 1, 'location': 'Area18'}),
        ('post', '/player/inventory/remove',  {'item': 'item-big', 'quantity': 1, 'location': 'Area18'}),
        ('get',  '/player/me',                None),
        ('get',  '/player/blueprints',        None),
    ]:
        resp = getattr(client, method)(path, headers=headers, json=payload)
        assert resp.status_code == 403, f'{method.upper()} {path} 應該擋掉已刪除的玩家'


def test_soft_deleted_player_cannot_refresh(client, deleted_player_headers):
    """不擋的話，被移除的人可以一路續發 access token 到 refresh token 過期。"""
    _, refresh_headers = deleted_player_headers
    assert client.post('/player/refresh', headers=refresh_headers).status_code == 403


def test_refresh_token_cannot_be_used_as_access_token(client, seed_master):
    """refresh token（30 天）不可以直接拿去打一般端點。

    這條之前是破的：玩家 token 用 additional_claims={'type': 'player'} 蓋掉了
    flask-jwt-extended 自己的保留 claim（access / refresh），導致兩種 token 的
    type 都變成 'player'，而 verify_token_type() 對非 refresh 端點只擋
    type == 'refresh' —— 於是 30 天的 refresh token 等同 access token 可用。
    """
    client.post('/player/register', json={
        'nickname': 'R', 'star_citizen_id': 'RefreshMe', 'password': 'pw-123456'})
    login = client.post('/player/login', json={
        'star_citizen_id': 'RefreshMe', 'password': 'pw-123456'}).get_json()
    refresh_headers = {'Authorization': f"Bearer {login['refresh_token']}"}

    for path in ('/player/me', '/player/inventory', '/player/blueprints'):
        assert client.get(path, headers=refresh_headers).status_code == 422, \
            f'{path} 接受了 refresh token'


def test_player_token_claims_do_not_clobber_reserved_type(client, seed_master):
    """直接檢查 claim：access 要是 access、refresh 要是 refresh。"""
    import jwt as pyjwt
    client.post('/player/register', json={
        'nickname': 'C', 'star_citizen_id': 'ClaimCheck', 'password': 'pw-123456'})
    b = client.post('/player/login', json={
        'star_citizen_id': 'ClaimCheck', 'password': 'pw-123456'}).get_json()

    access = pyjwt.decode(b['token'], options={'verify_signature': False})
    refresh = pyjwt.decode(b['refresh_token'], options={'verify_signature': False})
    assert access['type'] == 'access'
    assert refresh['type'] == 'refresh'
    # 玩家身分改用不會撞名的 claim
    assert access.get('is_player') is True
    assert refresh.get('is_player') is True


def test_active_player_still_works(client, seed_master):
    """對照組：沒被刪除的玩家一切照常（確認上面的檢查沒有擋錯人）。"""
    client.post('/player/register', json={
        'nickname': '正常人', 'star_citizen_id': 'Alive', 'password': 'pw-123456'})
    login = client.post('/player/login', json={
        'star_citizen_id': 'Alive', 'password': 'pw-123456'}).get_json()
    headers = {'Authorization': f"Bearer {login['token']}"}

    assert client.get('/player/me', headers=headers).status_code == 200
    assert client.get('/player/inventory', headers=headers).status_code == 200
    assert client.post('/player/inventory/add', headers=headers, json={
        'item': 'item-big', 'quantity': 3, 'location': 'Area18'}).status_code in (200, 201)
    assert client.post('/player/refresh', headers={
        'Authorization': f"Bearer {login['refresh_token']}"}).status_code == 200


def test_display_names_by_scid_empty_input(client):
    """空輸入不該打 DB，也不該炸。"""
    from src.models.player import Player
    assert Player.display_names_by_scid([]) == {}
    assert Player.display_names_by_scid([None, '']) == {}


# ─────────────────────────────────────────────────────── 主檔 API

def test_item_search(client, auth_headers, seed_master):
    body = client.get('/item/search?q=agri', headers=auth_headers).get_json()
    assert len(body['data']) == 1
    assert body['data'][0]['name'] == 'Agricium'
    assert body['data'][0]['volume_scu'] == 1.0


def test_item_search_requires_q(client, auth_headers):
    assert client.get('/item/search', headers=auth_headers).status_code == 400


def test_item_search_escapes_regex(client, auth_headers, seed_master):
    """使用者輸入的 regex 特殊字元不該被當語法（也不該 500）。"""
    resp = client.get('/item/search?q=.*', headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()['data'] == []


def test_item_search_matches_chinese_name(client, auth_headers, seed_master):
    """打中文名也要找得到——之前只比對英文 name_lower／class_name，
    跟 BlueprintMaster.search() 已經在比對 name_zh 不一致（見那邊的說明）。
    「查詢」頁的「物品名稱」自動完成欄位需要中英文都找得到。"""
    from src.mongo import get_db
    get_db()['item_master'].update_one(
        {'_id': 'item-big'}, {'$set': {'name_zh': '阿格瑞西姆'}})
    body = client.get('/item/search?q=阿格瑞西姆', headers=auth_headers).get_json()
    assert [r['name'] for r in body['data']] == ['Agricium']
    assert body['data'][0]['name_zh'] == '阿格瑞西姆'


def test_item_detail_hides_raw_by_default(client, auth_headers):
    get_db()['item_master'].insert_one({**ITEM_BIG, 'raw': {'big': 'payload'}})

    body = client.get('/item/item-big', headers=auth_headers).get_json()
    assert 'raw' not in body['data']

    body = client.get('/item/item-big?with_raw=1', headers=auth_headers).get_json()
    assert body['data']['raw'] == {'big': 'payload'}


def test_item_prices_falls_back_to_wiki(client, auth_headers):
    """沒有 UEX 資料時要退回 Wiki API 內嵌價格。"""
    get_db()['item_master'].insert_one({**ITEM_BIG, 'raw': {'uex_prices': {'purchase': [
        {'price_buy': 1508220, 'terminal_name': 'New Deal - Lorville',
         'starmap_location': {'name': 'Lorville'}, 'game_version': '4.9.0-LIVE'},
    ]}}})

    body = client.get('/item/item-big/prices', headers=auth_headers).get_json()
    assert body['source'] == 'wiki'
    assert body['data'][0]['price_buy'] == 1508220
    assert body['data'][0]['location'] == 'Lorville'


def test_item_prices_empty_is_not_error(client, auth_headers, seed_master):
    body = client.get('/item/item-small/prices', headers=auth_headers).get_json()
    assert body['success'] is True
    assert body['data'] == []


def test_sync_status(client, auth_headers, seed_master):
    from datetime import datetime
    get_db()['sync_runs'].insert_one({
        '_id': 'run-1', 'started_at': datetime.utcnow(),
        'finished_at': datetime.utcnow(), 'ok': True, 'errors': [],
        'stats': [{'resource': 'items'}],
    })

    body = client.get('/item/sync-status', headers=auth_headers).get_json()
    assert body['data']['counts']['items'] == 2
    assert body['data']['counts']['vehicles'] == 1
    assert body['data']['latest_run']['ok'] is True
    assert 'stats' not in body['data']['latest_run'], 'stats 太大，列表不該回傳'
    assert body['data']['is_running'] is False, '沒有鎖存在時不該顯示成執行中'


def test_sync_status_reflects_held_lock(client, auth_headers):
    """worker 沒開時任務只是卡在佇列，latest_run 不會變——is_running 得看鎖，
    不能只看 latest_run，不然畫面上完全看不出「其實根本沒在跑」。"""
    import tasks.scdata_sync as sync_mod

    with sync_mod.sync_lock('run-in-progress') as acquired:
        assert acquired is True
        body = client.get('/item/sync-status', headers=auth_headers).get_json()
        assert body['data']['is_running'] is True

    body = client.get('/item/sync-status', headers=auth_headers).get_json()
    assert body['data']['is_running'] is False, '離開 lock 之後應該解鎖'


def test_sync_runs_returns_recent_history(client, auth_headers):
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    get_db()['sync_runs'].insert_many([
        {'_id': 'run-old', 'started_at': now - timedelta(days=1),
         'finished_at': now - timedelta(days=1), 'ok': True, 'errors': [],
         'stats': [{'resource': 'items', 'seen': 10, 'written': 2, 'retired': 0}]},
        {'_id': 'run-new', 'started_at': now, 'finished_at': now,
         'ok': False, 'errors': ['items: boom'],
         'stats': [{'resource': 'items', 'seen': 10, 'written': 0, 'retired': 0}]},
    ])

    body = client.get('/item/sync-runs', headers=auth_headers).get_json()
    assert body['success'] is True
    ids = [r['_id'] for r in body['data']]
    assert ids == ['run-new', 'run-old'], '應該依 started_at 新到舊排序'
    assert all('stats' not in r for r in body['data']), '歷史列表不該帶逐資源明細'
    assert body['data'][0]['ok'] is False
    assert body['data'][0]['errors'] == ['items: boom']


def test_sync_runs_limit_is_capped(client, auth_headers):
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    get_db()['sync_runs'].insert_many([
        {'_id': f'run-{i}', 'started_at': now - timedelta(minutes=i),
         'finished_at': now - timedelta(minutes=i), 'ok': True, 'errors': [], 'stats': []}
        for i in range(150)
    ])

    body = client.get('/item/sync-runs?limit=9999', headers=auth_headers).get_json()
    assert len(body['data']) == 100, 'limit 應被夾到上限 100'


def test_sync_schedule_includes_next_run(client, auth_headers):
    """後台排程頁要顯示「下次執行時間」，GET/PUT 都得回這個欄位。"""
    body = client.get('/item/sync-schedule', headers=auth_headers).get_json()
    assert body['success'] is True
    assert 'next_run' in body['data']
    assert body['data']['next_run'] is not None, '預設排程是啟用的，應該算得出下次執行時間'

    put_body = client.put('/item/sync-schedule', headers=auth_headers,
                           json={'cron': '0 4 * * *', 'enabled': False}).get_json()
    assert put_body['success'] is True
    assert put_body['data']['next_run'] is None, '停用排程後不該有下次執行時間'


def test_paging_limit_is_capped(client, auth_headers, seed_master):
    body = client.get('/item/?limit=9999', headers=auth_headers).get_json()
    assert body['limit'] == 200, 'limit 應被夾到 MAX_LIMIT'


def test_paging_handles_garbage(client, auth_headers, seed_master):
    body = client.get('/item/?limit=abc&offset=xyz', headers=auth_headers).get_json()
    assert body['limit'] == 50 and body['offset'] == 0
