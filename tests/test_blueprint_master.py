"""製造藍圖主檔（blueprint_master）的映射、查詢與玩家名冊連動測試。

## 資料形狀來自真實 API

下面 `API_ROW` 是 2026-08 實際打
`GET https://api.star-citizen.wiki/api/blueprints?include=ingredients,output,dismantle_returns`
取回的第一筆，欄位名稱與嵌套結構照抄。若上游改欄位，這支測試會先壞掉，
而不是等到同步完才發現主檔一片空白。

## 兩個容易搞混的 collection

  - `blueprint_master` ＝ 遊戲裡有哪些配方（API 同步、唯讀、1,600+ 筆）
  - `blueprints`       ＝ 某位玩家擁有哪張藍圖（人填的名冊）

靠 `blueprints.blueprint_uuid` 連起來，而且允許為空。
"""
import pytest

from src.models.blueprint import DEFAULT_UNLOCK_STATUS, HOLDER_HIDDEN_STATUSES  # noqa: F401
from src.models.blueprint import Blueprint as BlueprintModel
from src.models.item import BlueprintMaster
from src.mongo import get_db
from src.scdata import WIKI_QUERY_EXTRA, WIKI_RESOURCES, map_blueprint

# 真實 API 回應的第一筆（含 include 帶出來的 ingredients / output / dismantle_returns）
API_ROW = {
    'uuid': '280f47b7-8434-410c-b854-380768fdccec',
    'key': 'BP_CRAFT_AMRS_LaserCannon_S1',
    'category_uuid': '61e576d2-f8b4-46b1-98e6-9205bb5de686',
    'output_item_uuid': '26838ca7-418a-47d2-8429-7339ebbb8993',
    'output_name': 'Omnisky III Cannon',
    'output_class': 'amrs_lasercannon_s1',
    'craft_time_seconds': 540,
    'craft_time_label': '9 minutes',
    'is_available_by_default': False,
    'game_version': '4.10.0-LIVE.12519617',
    'ingredient_count': 3,
    'unlocking_missions_count': 1,
    'ingredients': [
        {'name': 'Agricium', 'kind': 'resource',
         'resource_type_uuid': 'res-agri', 'item_uuid': None,
         'quantity_scu': 0.36, 'quantity': None},
        {'name': 'Hadanite', 'kind': 'resource',
         'resource_type_uuid': 'res-hada', 'item_uuid': None,
         'quantity_scu': None, 'quantity': 7},
        {'name': 'Dolivine', 'kind': 'resource',
         'resource_type_uuid': 'res-doli', 'item_uuid': None,
         'quantity_scu': None, 'quantity': 7},
    ],
    'dismantle_returns': [
        {'name': 'Agricium', 'resource_type_uuid': 'res-agri', 'quantity_scu': 0.18},
    ],
    'output': {
        'uuid': '26838ca7-418a-47d2-8429-7339ebbb8993',
        'name': 'Omnisky III Cannon',
        'class': 'amrs_lasercannon_s1',
        'type': 'WeaponGun',
        'type_label': 'Vehicle Weapon',
        'sub_type': 'Gun',
        'grade': 'A',
    },
    'web_url': 'https://api.star-citizen.wiki/blueprints/omnisky-iii-cannon',
}


# ═══════════════════════════════════════════════════════════
#  同步設定
# ═══════════════════════════════════════════════════════════

def test_blueprints_registered_as_wiki_resource():
    assert 'blueprints' in WIKI_RESOURCES
    collection, mapper = WIKI_RESOURCES['blueprints']
    assert collection == 'blueprint_master'
    assert mapper is map_blueprint


def test_blueprints_list_request_asks_for_include():
    """沒有 include 的話列表回應的 ingredients 是空的。

    這是這次整合最關鍵的一個參數 —— 沒有它就得逐筆打 1,606 次明細端點，
    同步請求數會從 33 變成 1,639。
    """
    extra = WIKI_QUERY_EXTRA.get('blueprints') or {}
    include = extra.get('include', '')
    for field in ('ingredients', 'output', 'dismantle_returns'):
        assert field in include, f'include 少了 {field}，列表回應會拿不到它'


# ═══════════════════════════════════════════════════════════
#  欄位映射
# ═══════════════════════════════════════════════════════════

def test_map_blueprint_flattens_expected_fields():
    doc = map_blueprint(API_ROW)

    assert doc['_id'] == API_ROW['uuid']
    assert doc['key'] == 'BP_CRAFT_AMRS_LaserCannon_S1'
    assert doc['name'] == 'Omnisky III Cannon'
    assert doc['name_lower'] == 'omnisky iii cannon'      # 前綴查詢要走索引
    # 對得上 item_master._id —— 這是能跟物品主檔 join 的關鍵
    assert doc['output_item_uuid'] == '26838ca7-418a-47d2-8429-7339ebbb8993'
    assert doc['output_type'] == 'WeaponGun'
    assert doc['output_type_label'] == 'Vehicle Weapon'
    assert doc['output_grade'] == 'A'
    assert doc['craft_time_seconds'] == 540
    assert doc['craft_time_label'] == '9 minutes'
    assert doc['is_available_by_default'] is False
    assert doc['ingredient_count'] == 3
    assert doc['unlocking_missions_count'] == 1
    assert doc['game_version'] == '4.10.0-LIVE.12519617'
    # 原始 JSON 整包留著，之後要加欄位不用重抓 API（比照 map_item）
    assert doc['raw'] == API_ROW


def test_map_blueprint_flattens_ingredients():
    doc = map_blueprint(API_ROW)

    assert len(doc['ingredients']) == 3
    agri = doc['ingredients'][0]
    assert agri == {
        'name': 'Agricium', 'kind': 'resource',
        'item_uuid': None, 'resource_type_uuid': 'res-agri',
        'quantity': None, 'quantity_scu': 0.36,
    }
    # 有些材料給數量、有些給體積，兩種都要保留
    assert doc['ingredients'][1]['quantity'] == 7
    assert doc['ingredients'][1]['quantity_scu'] is None

    assert doc['dismantle_returns'] == [
        {'name': 'Agricium', 'resource_type_uuid': 'res-agri', 'quantity_scu': 0.18},
    ]


def test_map_blueprint_without_include_still_maps():
    """沒帶 include 時 ingredients/output 是空的，不能因此炸掉。"""
    row = dict(API_ROW, ingredients=[], dismantle_returns=[], output={})
    doc = map_blueprint(row)

    assert doc['name'] == 'Omnisky III Cannon'   # 退回 output_name
    assert doc['ingredients'] == []
    assert doc['output_type'] is None


def test_map_blueprint_rejects_row_without_uuid():
    assert map_blueprint({'output_name': 'X'}) is None


# ═══════════════════════════════════════════════════════════
#  模型查詢
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def seeded_master(app):
    """塞幾筆主檔資料（模擬同步後的狀態）。"""
    db = get_db()
    docs = [
        dict(map_blueprint(API_ROW), is_current=True),
        dict(map_blueprint(dict(
            API_ROW, uuid='bp-2', key='BP_CRAFT_MEDPEN',
            output_name='Medical Pen', output_item_uuid='item-medpen',
            ingredient_count=1, craft_time_seconds=60,
            output={'type': 'Consumable', 'type_label': 'Consumable'},
        )), is_current=True),
        # 已從遊戲移除的舊配方
        dict(map_blueprint(dict(
            API_ROW, uuid='bp-old', output_name='Retired Gun',
            output_item_uuid='item-old',
        )), is_current=False),
    ]
    db['blueprint_master'].insert_many(docs)
    return docs


def test_search_matches_name_prefix(seeded_master):
    rows = BlueprintMaster.search('omni')
    assert [r['name'] for r in rows] == ['Omnisky III Cannon']


def test_search_matches_key(seeded_master):
    """_MasterBase 比對的是 class_name，藍圖主檔沒有那欄 —— 對應的是 key。

    如果 BlueprintMaster 沒有覆寫 search()，這個測試會失敗。
    """
    rows = BlueprintMaster.search('BP_CRAFT_MEDPEN')
    assert [r['name'] for r in rows] == ['Medical Pen']


def test_search_excludes_retired_by_default(seeded_master):
    assert BlueprintMaster.search('Retired') == []
    assert len(BlueprintMaster.search('Retired', include_retired=True)) == 1


def test_get_returns_full_recipe_without_raw(seeded_master):
    doc = BlueprintMaster.get(API_ROW['uuid'])
    assert len(doc['ingredients']) == 3
    # raw 是整包 API JSON，回應不該帶它
    assert 'raw' not in doc


def test_for_output_item_joins_by_item_uuid(seeded_master):
    """「做出這個物品的配方」—— 這是跟 item_master join 的主要路徑。"""
    rows = BlueprintMaster.for_output_item('26838ca7-418a-47d2-8429-7339ebbb8993')
    assert [r['name'] for r in rows] == ['Omnisky III Cannon']
    # 已下架的配方不該出現
    assert BlueprintMaster.for_output_item('item-old') == []


def test_output_types_lists_only_current(seeded_master):
    assert BlueprintMaster.output_types() == ['Consumable', 'WeaponGun']


def test_list_all_filters_by_type(seeded_master):
    rows, total = BlueprintMaster.list_all(output_type='Consumable')
    assert total == 1
    assert rows[0]['name'] == 'Medical Pen'


# ═══════════════════════════════════════════════════════════
#  路由優先序（真的踩過類似的坑）
# ═══════════════════════════════════════════════════════════

def test_master_routes_are_not_swallowed_by_id_route(client, auth_headers, seeded_master):
    """`/blueprint/master` 不能被 `/blueprint/<blueprint_id>` 吃掉。

    兩條規則都能匹配 `/blueprint/master`。Werkzeug 會偏好靜態片段，
    所以應該命中 list_master —— 但這是「應該」，值得用測試釘住，
    否則 `/blueprint/master` 會變成「查一個 id 叫 master 的玩家藍圖」，
    安靜地回 404。
    """
    resp = client.get('/blueprint/master', headers=auth_headers)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    # 主檔列表有 total；玩家名冊的單筆查詢沒有
    assert 'total' in body, '打到玩家名冊的 <blueprint_id> 路由了'
    assert body['total'] == 2      # 兩筆 is_current=True


def test_master_search_endpoint(client, auth_headers, seeded_master):
    resp = client.get('/blueprint/master/search?q=medical', headers=auth_headers)
    assert resp.status_code == 200
    assert [r['name'] for r in resp.get_json()['data']] == ['Medical Pen']


def test_master_search_requires_query(client, auth_headers):
    resp = client.get('/blueprint/master/search', headers=auth_headers)
    assert resp.status_code == 400


def test_master_detail_endpoint(client, auth_headers, seeded_master):
    resp = client.get(f'/blueprint/master/{API_ROW["uuid"]}', headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['craft_time_label'] == '9 minutes'
    assert len(data['ingredients']) == 3


def test_master_detail_404(client, auth_headers):
    resp = client.get('/blueprint/master/does-not-exist', headers=auth_headers)
    assert resp.status_code == 404


def test_master_for_item_endpoint(client, auth_headers, seeded_master):
    resp = client.get(
        '/blueprint/master/for-item/26838ca7-418a-47d2-8429-7339ebbb8993',
        headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()['data']) == 1


# ═══════════════════════════════════════════════════════════
#  玩家名冊 ←→ 主檔連動
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def player_headers(client):
    client.post('/player/register', json={
        'nickname': 'Pilot', 'star_citizen_id': 'Pilot', 'password': 'pw-123456',
    })
    login = client.post('/player/login', json={
        'star_citizen_id': 'Pilot', 'password': 'pw-123456',
    })
    return {'Authorization': f"Bearer {login.get_json()['token']}"}


def test_player_can_register_blueprint_from_master(client, player_headers, seeded_master):
    """帶 blueprint_uuid 時以主檔的正式名稱為準（避免同一張藍圖出現多種寫法）。"""
    resp = client.post('/player/blueprints', headers=player_headers, json={
        'name': '打錯字的名稱',
        'blueprint_uuid': API_ROW['uuid'],
    })
    assert resp.status_code == 201, resp.get_json()

    listed = client.get('/player/blueprints', headers=player_headers).get_json()['data']
    assert len(listed) == 1
    assert listed[0]['name'] == 'Omnisky III Cannon'   # 用主檔的名稱
    assert listed[0]['blueprint_uuid'] == API_ROW['uuid']


def test_player_blueprint_list_is_enriched_with_master(client, player_headers, seeded_master):
    """有連到主檔的要帶出配方摘要，前端才能顯示「需要什麼材料」。"""
    client.post('/player/blueprints', headers=player_headers,
                json={'blueprint_uuid': API_ROW['uuid']})

    row = client.get('/player/blueprints', headers=player_headers).get_json()['data'][0]
    assert row['master'] is not None
    assert row['master']['craft_time_label'] == '9 minutes'
    assert row['master']['ingredient_count'] == 3


def test_player_cannot_use_free_text(client, player_headers, seeded_master):
    """玩家端**不接受**自由輸入的名稱，只能選主檔裡有的。

    同一張藍圖若每個人自己打字，會出現「Omnisky III」「omnisky 3」好幾種
    寫法，「誰有這張圖」（/blueprint/holders）就分不成同一組。
    後台（app/blueprint/view.py）仍可自由輸入，當作例外處理的逃生門。
    """
    resp = client.post('/player/blueprints', headers=player_headers,
                       json={'name': '某張還沒進主檔的藍圖'})
    assert resp.status_code == 400
    assert '選擇' in resp.get_json()['message']

    listed = client.get('/player/blueprints', headers=player_headers).get_json()['data']
    assert listed == []


def test_player_blueprint_name_always_comes_from_master(client, player_headers, seeded_master):
    """就算 client 硬塞 name，也要以主檔的名稱為準。"""
    resp = client.post('/player/blueprints', headers=player_headers, json={
        'name': '我亂打的名稱',
        'blueprint_uuid': API_ROW['uuid'],
    })
    assert resp.status_code == 201

    row = client.get('/player/blueprints', headers=player_headers).get_json()['data'][0]
    assert row['name'] == 'Omnisky III Cannon'


def test_existing_free_text_records_still_display(client, player_headers, seeded_master):
    """既有的自由輸入紀錄（改規則之前留下的）仍要能正常顯示，不能壞掉。"""
    from src.models.player import Player
    player = Player.find_by_star_citizen_id('Pilot')
    BlueprintModel.create(name='舊制自由輸入的圖', player_id=str(player['_id']))

    rows = client.get('/player/blueprints', headers=player_headers).get_json()['data']
    assert len(rows) == 1
    assert rows[0]['name'] == '舊制自由輸入的圖'
    assert rows[0]['blueprint_uuid'] is None
    assert rows[0]['master'] is None      # 沒有主檔資料，不該炸掉


def test_player_cannot_register_invalid_master_uuid(client, player_headers, seeded_master):
    resp = client.post('/player/blueprints', headers=player_headers,
                       json={'blueprint_uuid': 'not-a-real-uuid'})
    assert resp.status_code == 400
    assert '找不到' in resp.get_json()['message']


def test_blueprint_uuid_is_indexed():
    """名冊按 blueprint_uuid join 主檔，要有索引。"""
    from src.mongo import ensure_indexes
    ensure_indexes()
    names = get_db()['blueprints'].index_information()
    assert any('blueprint_uuid' in str(v.get('key', '')) for v in names.values()), \
        'blueprints.blueprint_uuid 沒有索引'


# ═══════════════════════════════════════════════════════════
#  「誰有這張藍圖」跨玩家查詢（/blueprint/holders）
#
#  這是藍圖版的 /inventory/where —— 玩家端「查詢 › 持有藍圖」在用。
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def three_players_with_blueprints(app, seeded_master):
    """建三個玩家，其中兩個有同一張主檔藍圖、一個有自由輸入的藍圖。"""
    from src.models.player import Player

    alice = Player.create(player_name='Alice', star_citizen_id='AliceSC',
                          nickname='艾莉絲', password='pw-123456')
    bob = Player.create(player_name='Bob', star_citizen_id='BobSC',
                        nickname='鮑伯', password='pw-123456')
    carol = Player.create(player_name='Carol', star_citizen_id='CarolSC',
                          nickname='卡蘿', password='pw-123456')

    BlueprintModel.create(name='Omnisky III Cannon', player_id=alice,
                          blueprint_uuid=API_ROW['uuid'], unlock_status='unlocked')
    BlueprintModel.create(name='Omnisky III Cannon', player_id=bob,
                          blueprint_uuid=API_ROW['uuid'], unlock_status='obtained')
    # 自由輸入的（沒有 uuid）
    BlueprintModel.create(name='某張還沒進主檔的圖', player_id=carol,
                          unlock_status='unconfirmed')
    return {'alice': alice, 'bob': bob, 'carol': carol}


def test_holders_groups_by_blueprint(app, three_players_with_blueprints):
    groups = BlueprintModel.find_holders()
    by_name = {g['name']: g for g in groups}

    assert by_name['Omnisky III Cannon']['holder_count'] == 2
    holders = by_name['Omnisky III Cannon']['holders']
    assert {h['nickname'] for h in holders} == {'艾莉絲', '鮑伯'}
    assert {h['unlock_status'] for h in holders} == {'unlocked', 'obtained'}


def test_holders_groups_free_text_separately(app, three_players_with_blueprints):
    """自由輸入的藍圖沒有 uuid，不能全部併成一組 null。"""
    groups = BlueprintModel.find_holders()
    names = {g['name'] for g in groups}
    assert '某張還沒進主檔的圖' in names

    free = next(g for g in groups if g['name'] == '某張還沒進主檔的圖')
    assert free['blueprint_uuid'] is None
    assert free['holder_count'] == 1


def test_holders_filters_by_query(app, three_players_with_blueprints):
    groups = BlueprintModel.find_holders(query='omnisky')
    assert len(groups) == 1
    assert groups[0]['name'] == 'Omnisky III Cannon'


def test_holders_excludes_soft_deleted_blueprints(app, three_players_with_blueprints):
    """玩家刪掉的藍圖不該出現在別人的查詢結果裡。"""
    ids = three_players_with_blueprints
    bp = BlueprintModel.find_all(player_id=ids['alice'])[0]
    BlueprintModel.soft_delete(bp['_id'])

    groups = BlueprintModel.find_holders(query='omnisky')
    assert groups[0]['holder_count'] == 1
    assert groups[0]['holders'][0]['nickname'] == '鮑伯'


def test_holders_excludes_soft_deleted_players(app, three_players_with_blueprints):
    """被軟刪除的玩家也不該出現。"""
    from src.models.player import Player
    Player.soft_delete(three_players_with_blueprints['bob'])

    groups = BlueprintModel.find_holders(query='omnisky')
    assert groups[0]['holder_count'] == 1
    assert groups[0]['holders'][0]['nickname'] == '艾莉絲'


def test_holders_does_not_leak_notes(app, seeded_master):
    """notes 是玩家寫給自己的備註，不該出現在別人的查詢結果裡。"""
    from src.models.player import Player
    pid = Player.create(player_name='Dave', star_citizen_id='DaveSC',
                        nickname='戴夫', password='pw-123456')
    BlueprintModel.create(name='Omnisky III Cannon', player_id=pid,
                          blueprint_uuid=API_ROW['uuid'],
                          notes='這是我的私人備註，不要給別人看')

    groups = BlueprintModel.find_holders(query='omnisky')
    serialised = str(groups)
    assert '私人備註' not in serialised, 'notes 外洩到跨玩家查詢結果'
    for holder in groups[0]['holders']:
        assert 'notes' not in holder


def test_holders_endpoint(client, player_headers, three_players_with_blueprints):
    """玩家 token 打得到這支（比照 /inventory/where，公會互查是功能需求）。"""
    resp = client.get('/blueprint/holders?q=omnisky', headers=player_headers)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['holder_count'] == 2


def test_holders_endpoint_requires_auth(client):
    assert client.get('/blueprint/holders').status_code == 401


# ── 「未取得」不該出現在「誰有這張藍圖」 ─────────────────────────
#
# 這個功能的用意是「找到有這張圖的人去問他能不能幫做」，列出標成未取得的人
# 會讓問的人白跑一趟。locked 只有管理員從後台設得出來。

def test_holders_hides_locked(app, seeded_master):
    from src.models.player import Player
    has = Player.create(player_name='Has', star_citizen_id='HasSC',
                        nickname='有的人', password='pw-123456')
    hasnt = Player.create(player_name='Hasnt', star_citizen_id='HasntSC',
                          nickname='沒有的人', password='pw-123456')

    BlueprintModel.create(name='Omnisky III Cannon', player_id=has,
                          blueprint_uuid=API_ROW['uuid'], unlock_status='obtained')
    BlueprintModel.create(name='Omnisky III Cannon', player_id=hasnt,
                          blueprint_uuid=API_ROW['uuid'], unlock_status='locked')

    groups = BlueprintModel.find_holders(query='omnisky')
    assert len(groups) == 1
    assert groups[0]['holder_count'] == 1
    assert [h['nickname'] for h in groups[0]['holders']] == ['有的人']


def test_holders_group_disappears_when_all_locked(app, seeded_master):
    """整組都是未取得時，那張藍圖根本不該出現在結果裡。"""
    from src.models.player import Player
    pid = Player.create(player_name='Nobody', star_citizen_id='NobodySC',
                        nickname='沒人', password='pw-123456')
    BlueprintModel.create(name='Omnisky III Cannon', player_id=pid,
                          blueprint_uuid=API_ROW['uuid'], unlock_status='locked')

    assert BlueprintModel.find_holders(query='omnisky') == []


def test_holders_keeps_unconfirmed_and_outdated(app, seeded_master):
    """未確認／已過時的人確實登記過，仍然值得問一聲，所以要留著。"""
    from src.models.player import Player
    a = Player.create(player_name='A', star_citizen_id='ASC',
                      nickname='未確認的人', password='pw-123456')
    b = Player.create(player_name='B', star_citizen_id='BSC',
                      nickname='過時的人', password='pw-123456')

    BlueprintModel.create(name='Omnisky III Cannon', player_id=a,
                          blueprint_uuid=API_ROW['uuid'], unlock_status='unconfirmed')
    BlueprintModel.create(name='Omnisky III Cannon', player_id=b,
                          blueprint_uuid=API_ROW['uuid'], unlock_status='outdated')

    groups = BlueprintModel.find_holders(query='omnisky')
    assert groups[0]['holder_count'] == 2
    # 狀態要一起回傳，前端才標得出來讓人自己判斷
    assert {h['unlock_status'] for h in groups[0]['holders']} == {'unconfirmed', 'outdated'}


def test_holders_hides_discord_by_default(app, seeded_master):
    """沒勾公開的人，Discord 不能出現在「誰有這張藍圖」裡。"""
    from src.models.player import Player
    pid = Player.create(player_name='Tom', star_citizen_id='TomSC', nickname='湯姆',
                        discord_name='tomli#1234', discord_id='9988',
                        password='pw-123456')
    BlueprintModel.create(name='Omnisky III Cannon', player_id=pid,
                          blueprint_uuid=API_ROW['uuid'])

    groups = BlueprintModel.find_holders(query='omnisky')
    holder = groups[0]['holders'][0]
    assert holder['discord_name'] == '' and holder['discord_id'] == ''
    assert 'discord_public' not in holder, '旗標本身不該回傳'
    assert 'tomli#1234' not in str(groups)


def test_holders_shows_discord_when_public(app, seeded_master):
    from src.models.player import Player
    pid = Player.create(player_name='Tom', star_citizen_id='TomSC', nickname='湯姆',
                        discord_name='tomli#1234', discord_id='9988',
                        discord_public=True, password='pw-123456')
    BlueprintModel.create(name='Omnisky III Cannon', player_id=pid,
                          blueprint_uuid=API_ROW['uuid'])

    holder = BlueprintModel.find_holders(query='omnisky')[0]['holders'][0]
    assert holder['discord_name'] == 'tomli#1234'
    assert holder['discord_id'] == '9988'


def test_holders_mixed_public_and_private(app, seeded_master):
    """同一組裡有人公開有人沒公開時，不能互相污染。"""
    from src.models.player import Player
    pub = Player.create(player_name='Pub', star_citizen_id='PubSC', nickname='公開的',
                        discord_name='public#1', discord_public=True, password='pw-123456')
    priv = Player.create(player_name='Priv', star_citizen_id='PrivSC', nickname='不公開的',
                         discord_name='private#2', password='pw-123456')
    for pid in (pub, priv):
        BlueprintModel.create(name='Omnisky III Cannon', player_id=pid,
                              blueprint_uuid=API_ROW['uuid'])

    holders = BlueprintModel.find_holders(query='omnisky')[0]['holders']
    by_nick = {h['nickname']: h for h in holders}
    assert by_nick['公開的']['discord_name'] == 'public#1'
    assert by_nick['不公開的']['discord_name'] == ''
    assert 'private#2' not in str(holders)


def test_player_registration_defaults_to_obtained(client, player_headers, seeded_master):
    """玩家自助登記不帶狀態時要落在 obtained —— 登記就是「我有」。"""
    resp = client.post('/player/blueprints', headers=player_headers,
                       json={'blueprint_uuid': API_ROW['uuid']})
    assert resp.status_code in (200, 201), resp.get_json()

    rows = client.get('/player/blueprints', headers=player_headers).get_json()['data']
    assert rows[0]['unlock_status'] == DEFAULT_UNLOCK_STATUS == 'obtained'
