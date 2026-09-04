"""批量登記藍圖（POST /player/blueprints/bulk）的測試。

重點在「重複」與「越權」兩件事：

- `blueprints` 沒有 (player_id, blueprint_uuid) 的唯一索引，單筆登記本來
  就能重複建立。批量登記把這件事放大 50 倍 —— 使用者手滑按兩下就會多出
  一整批重複資料，而「誰有這張圖」的統計會跟著失真。所以已登記的一律跳過。
- 名稱一律取自主檔、狀態一律寫死，跟單筆登記同一套規則（否則玩家可以
  用 locked 把自己從「誰有這張藍圖」的結果裡藏起來）。
"""
import pytest

from src.models.blueprint import (DEFAULT_UNLOCK_STATUS,
                                  Blueprint as BlueprintModel)
from src.models.player import Player
from src.mongo import get_db


@pytest.fixture
def master():
    """三張藍圖主檔。

    `name_lower` 一定要有 —— 那是名稱查詢實際比對的欄位（見
    src/scdata.py 的 map_blueprint，同步時就會寫入），少了它
    測試資料就跟正式資料長得不一樣，測到的東西也不算數。
    """
    get_db()['blueprint_master'].insert_many([
        {'_id': 'bp-1', 'name': 'Laser Cannon S1', 'name_lower': 'laser cannon s1',
         'name_zh': '雷射砲 S1', 'is_current': True, 'output_type': 'weapon'},
        {'_id': 'bp-2', 'name': 'Medical Pen', 'name_lower': 'medical pen',
         'name_zh': '醫療筆', 'is_current': True, 'output_type': 'consumable'},
        {'_id': 'bp-3', 'name': 'Shield Gen', 'name_lower': 'shield gen',
         'is_current': True, 'output_type': 'component'},
    ])


@pytest.fixture
def player_token(client, master):
    Player.create(player_name='Tom', star_citizen_id='Tom_SC', password='hunter22')
    resp = client.post('/player/login', json={
        'star_citizen_id': 'Tom_SC', 'password': 'hunter22'})
    return resp.get_json()['token']


@pytest.fixture
def headers(player_token):
    return {'Authorization': f'Bearer {player_token}'}


def _mine():
    player = Player.find_by_star_citizen_id('Tom_SC')
    return BlueprintModel.find_all(player_id=player['_id'])


# ── 正常批量登記 ──────────────────────────────────────────────

def test_bulk_registers_every_selected_blueprint(client, headers):
    resp = client.post('/player/blueprints/bulk', headers=headers,
                       json={'blueprint_uuids': ['bp-1', 'bp-2', 'bp-3']})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['added'] == 3
    assert body['skipped'] == 0
    assert len(_mine()) == 3


def test_names_come_from_master_not_the_client(client, headers):
    """client 傳什麼名稱都不看 —— 否則同一張圖會出現好幾種寫法，
    「誰有這張藍圖」就分不成同一組。"""
    client.post('/player/blueprints/bulk', headers=headers,
                json={'blueprint_uuids': ['bp-1'], 'name': '我自己亂打的名字'})
    assert [row['name'] for row in _mine()] == ['Laser Cannon S1']


def test_unlock_status_is_forced(client, headers):
    client.post('/player/blueprints/bulk', headers=headers,
                json={'blueprint_uuids': ['bp-1'], 'unlock_status': 'locked'})
    assert _mine()[0]['unlock_status'] == DEFAULT_UNLOCK_STATUS


def test_optional_fields_are_applied_to_all(client, headers):
    client.post('/player/blueprints/bulk', headers=headers, json={
        'blueprint_uuids': ['bp-1', 'bp-2'],
        'acquisition_method': '任務獎勵', 'notes': '4.10 一次解鎖',
    })
    rows = _mine()
    assert {row['acquisition_method'] for row in rows} == {'任務獎勵'}
    assert {row['notes'] for row in rows} == {'4.10 一次解鎖'}


# ── 重複 ──────────────────────────────────────────────────────

def test_already_registered_are_skipped_not_duplicated(client, headers):
    client.post('/player/blueprints/bulk', headers=headers,
                json={'blueprint_uuids': ['bp-1', 'bp-2']})
    resp = client.post('/player/blueprints/bulk', headers=headers,
                       json={'blueprint_uuids': ['bp-1', 'bp-2', 'bp-3']})

    body = resp.get_json()
    assert body['added'] == 1        # 只有 bp-3 是新的
    assert body['skipped'] == 2
    assert len(_mine()) == 3         # 不是 5


def test_double_click_does_not_double_register(client, headers):
    """手滑按兩下送出同一批 —— 這是批量登記最容易發生的意外。"""
    payload = {'blueprint_uuids': ['bp-1', 'bp-2', 'bp-3']}
    client.post('/player/blueprints/bulk', headers=headers, json=payload)
    client.post('/player/blueprints/bulk', headers=headers, json=payload)
    assert len(_mine()) == 3


def test_duplicate_uuids_within_one_request_are_deduped(client, headers):
    resp = client.post('/player/blueprints/bulk', headers=headers,
                       json={'blueprint_uuids': ['bp-1', 'bp-1', 'bp-1']})
    assert resp.get_json()['added'] == 1
    assert len(_mine()) == 1


def test_deleted_registration_can_be_registered_again(client, headers):
    """自己刪掉之後應該可以重新登記（軟刪除的不算已登記）。"""
    client.post('/player/blueprints/bulk', headers=headers,
                json={'blueprint_uuids': ['bp-1']})
    client.delete(f"/player/blueprints/{_mine()[0]['_id']}", headers=headers)

    resp = client.post('/player/blueprints/bulk', headers=headers,
                       json={'blueprint_uuids': ['bp-1']})
    assert resp.get_json()['added'] == 1


# ── 錯誤輸入 ──────────────────────────────────────────────────

def test_unknown_uuid_is_reported_not_registered(client, headers):
    resp = client.post('/player/blueprints/bulk', headers=headers,
                       json={'blueprint_uuids': ['bp-1', '不存在的uuid']})
    body = resp.get_json()
    assert body['added'] == 1
    assert body['not_found'] == 1
    assert len(_mine()) == 1


def test_empty_selection_is_rejected(client, headers):
    for payload in ({'blueprint_uuids': []}, {}, {'blueprint_uuids': 'bp-1'}):
        resp = client.post('/player/blueprints/bulk', headers=headers, json=payload)
        assert resp.status_code == 400


def test_over_the_cap_is_rejected(client, headers):
    from app.player.view import MAX_BULK_BLUEPRINTS
    resp = client.post('/player/blueprints/bulk', headers=headers, json={
        'blueprint_uuids': [f'uuid-{i}' for i in range(MAX_BULK_BLUEPRINTS + 1)]})
    assert resp.status_code == 400
    assert str(MAX_BULK_BLUEPRINTS) in resp.get_json()['message']


def test_requires_a_player_token(client, headers, auth_headers, master):
    """未登入不行；後台 admin token 也不行 —— 這支是「登記到自己名下」，
    admin 沒有『自己』可以登記。"""
    assert client.post('/player/blueprints/bulk',
                       json={'blueprint_uuids': ['bp-1']}).status_code == 401
    assert client.post('/player/blueprints/bulk', headers=auth_headers,
                       json={'blueprint_uuids': ['bp-1']}).status_code == 403


def test_registers_to_the_caller_only(client, headers, master):
    """另一位玩家的名下不該被寫入東西。"""
    other = Player.create(player_name='Bob', star_citizen_id='Bob_SC')
    client.post('/player/blueprints/bulk', headers=headers,
                json={'blueprint_uuids': ['bp-1', 'bp-2']})
    assert BlueprintModel.find_all(player_id=other) == []


# ── 已登記清單（畫面用來標記與禁止再勾）─────────────────────

def test_registered_uuids_helper(client, headers, master):
    player = Player.find_by_star_citizen_id('Tom_SC')
    assert BlueprintModel.registered_uuids_for_player(player['_id']) == set()

    client.post('/player/blueprints/bulk', headers=headers,
                json={'blueprint_uuids': ['bp-1', 'bp-3']})
    assert BlueprintModel.registered_uuids_for_player(player['_id']) == {'bp-1', 'bp-3'}
    # 只查其中幾筆
    assert BlueprintModel.registered_uuids_for_player(
        player['_id'], ['bp-1', 'bp-2']) == {'bp-1'}


def test_registered_uuids_with_malformed_player_id():
    assert BlueprintModel.registered_uuids_for_player('not-an-objectid') == set()


# ── 主檔清單的名稱篩選（畫面要能一邊篩一邊翻頁）───────────────

def test_master_list_filters_by_name(client, auth_headers, master):
    rows = client.get('/blueprint/master?q=medical',
                      headers=auth_headers).get_json()
    assert [row['_id'] for row in rows['data']] == ['bp-2']
    assert rows['total'] == 1


def test_master_list_name_filter_matches_chinese(client, auth_headers, master):
    rows = client.get('/blueprint/master?q=雷射', headers=auth_headers).get_json()
    assert [row['_id'] for row in rows['data']] == ['bp-1']


def test_master_list_name_filter_escapes_regex(client, auth_headers, master):
    """使用者輸入的 .* 不該被當成 regex 語法（會撈回全部）。"""
    rows = client.get('/blueprint/master?q=.*', headers=auth_headers).get_json()
    assert rows['total'] == 0


def test_master_list_combines_name_and_type_filter(client, auth_headers, master):
    rows = client.get('/blueprint/master?q=e&output_type=consumable',
                      headers=auth_headers).get_json()
    assert [row['_id'] for row in rows['data']] == ['bp-2']


# ── 這一輪安全性複查補上的防護 ────────────────────────────────

def test_unique_index_catches_the_concurrent_race(client, headers, master):
    """並發送出兩批相同的藍圖時，唯一索引要擋住第二筆並歸類成 skipped。

    「先查已登記、再 insert_many」是 read-then-write，不是原子操作：
    兩個分頁同時送出（或 client 對慢回應重試）會同時讀到「都還沒登記」
    然後雙雙寫入。這裡用 monkeypatch 讓已登記查詢回空集合，
    模擬「讀到的是過時狀態」那一瞬間。
    """
    from src.mongo import ensure_indexes
    ensure_indexes()

    player = Player.find_by_star_citizen_id('Tom_SC')
    BlueprintModel.bulk_create_for_player(
        player['_id'], [{'uuid': 'bp-1', 'name': 'Laser Cannon S1'}])

    original = BlueprintModel.registered_uuids_for_player.__func__
    BlueprintModel.registered_uuids_for_player = classmethod(
        lambda cls, pid, uuids=None: set())
    try:
        result = BlueprintModel.bulk_create_for_player(
            player['_id'], [{'uuid': 'bp-1', 'name': 'Laser Cannon S1'},
                            {'uuid': 'bp-2', 'name': 'Medical Pen'}])
    finally:
        BlueprintModel.registered_uuids_for_player = classmethod(original)

    # bp-1 撞索引 → 算 skipped；bp-2 照樣寫進去（ordered=False）
    assert result['added'] == ['bp-2']
    assert 'bp-1' in result['skipped']
    assert len(BlueprintModel.find_all(player_id=player['_id'])) == 2


def test_unique_index_still_allows_free_text_blueprints(master):
    """後台可以自由輸入名稱（blueprint_uuid 為 null），那種重複是允許的。"""
    from src.mongo import ensure_indexes
    ensure_indexes()

    pid = Player.create(player_name='Bob', star_citizen_id='Bob_SC')
    BlueprintModel.create(name='自己打的名字', player_id=pid)
    BlueprintModel.create(name='自己打的名字', player_id=pid)
    assert len(BlueprintModel.find_all(player_id=pid)) == 2


def test_oversized_payload_is_rejected_before_processing(client, headers):
    """上限要在逐項處理**之前**檢查 —— 否則 150 萬筆的 body 會先被
    str()/strip() 掃過一遍才被擋，單一請求就吃掉上百 MB 記憶體。"""
    from app.player.view import MAX_BULK_BLUEPRINTS
    resp = client.post('/player/blueprints/bulk', headers=headers, json={
        'blueprint_uuids': ['bp-1'] * (MAX_BULK_BLUEPRINTS + 50)})
    assert resp.status_code == 400
    assert '這次送出了' in resp.get_json()['message']


def test_absurdly_long_uuids_do_not_500(client, headers, master):
    """超長字串會組出超過 Mongo 16MB 命令上限的 $in → DocumentTooLarge → 500。
    現在會被長度檢查濾掉，當成查不到處理。"""
    resp = client.post('/player/blueprints/bulk', headers=headers, json={
        'blueprint_uuids': ['bp-1', 'x' * 70_000]})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['added'] == 1
    assert len(_mine()) == 1


def test_player_blueprint_list_is_not_truncated_at_500(client, headers, master):
    """批量登記頁靠這支端點判斷「哪些已登記」。被 500 截斷的話，
    後面的圖會顯示成可勾選 —— 畫面說謊。"""
    player = Player.find_by_star_citizen_id('Tom_SC')
    get_db()['blueprints'].insert_many([{
        'name': f'BP {i}', 'player_id': __import__('bson').ObjectId(player['_id']),
        'blueprint_uuid': f'uuid-{i:04d}', 'unlock_status': 'obtained',
        'deleted_at': None, 'notes': '', 'acquisition_method': '',
        'acquisition_location': '',
    } for i in range(600)])

    rows = client.get('/player/blueprints', headers=headers).get_json()['data']
    assert len(rows) == 600
