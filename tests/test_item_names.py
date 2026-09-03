"""異動紀錄補物品名稱：批次查詢與回傳形狀的迴歸測試。

原本 `app/inventory/view.py` 與 `app/player/view.py` 各有一份逐筆
`ItemMaster.get()` 的迴圈（一頁最多 200 筆 → 最多 200 次往返，而且
`get()` 沒有 projection，每次連整包 `raw` 一起撈回來只為了取兩個字串）。
兩份還開始漂移：player 版有 `item_name_zh`，inventory 版沒有。

這支測試鎖住三件事：只打一次 DB、兩支端點形狀一致、名稱查不到時
退回 uuid（不要留空白給前端）。
"""
import pytest

from app._shared import attach_item_names
from src.models.item import ItemMaster


@pytest.fixture
def seed_items():
    """兩筆物品主檔，其中一筆有中文名。"""
    col = ItemMaster._col()
    col.insert_many([
        {'_id': 'uuid-medpen', 'name': 'MedPen', 'name_zh': '醫療筆',
         'raw': {'padding': 'x' * 1000}},
        {'_id': 'uuid-ammo', 'name': 'Ammo Box', 'raw': {'padding': 'y' * 1000}},
    ])
    yield


def test_names_by_ids_batches_and_projects(seed_items):
    out = ItemMaster.names_by_ids(['uuid-medpen', 'uuid-ammo'])
    assert out == {
        'uuid-medpen': {'name': 'MedPen', 'name_zh': '醫療筆'},
        'uuid-ammo':   {'name': 'Ammo Box', 'name_zh': None},
    }
    # 不該把整包 raw 帶回來 —— projection 的重點就在這
    assert 'raw' not in str(out)


def test_names_by_ids_ignores_empty_input():
    assert ItemMaster.names_by_ids([]) == {}
    assert ItemMaster.names_by_ids([None, '']) == {}


def test_attach_item_names_hits_the_db_once(seed_items, monkeypatch):
    """20 列、2 種物品 —— 不管幾列都只能查一次。"""
    calls = []
    original = ItemMaster.names_by_ids.__func__

    def counting(cls, ids):
        ids = list(ids)
        calls.append(ids)
        return original(cls, ids)

    monkeypatch.setattr(ItemMaster, 'names_by_ids', classmethod(counting))

    rows = [{'item_id': 'uuid-medpen' if i % 2 else 'uuid-ammo'} for i in range(20)]
    attach_item_names(rows)

    assert len(calls) == 1
    assert len(calls[0]) == 20   # 去重交給 names_by_ids，呼叫端不必先整理


def test_attach_item_names_never_calls_get(seed_items, monkeypatch):
    """逐筆 get() 是舊寫法，回來就是效能退步。"""
    def boom(*args, **kwargs):
        raise AssertionError('attach_item_names 不該逐筆呼叫 ItemMaster.get()')

    monkeypatch.setattr(ItemMaster, 'get', classmethod(boom))
    attach_item_names([{'item_id': 'uuid-medpen'}])


def test_attach_item_names_fills_both_fields(seed_items):
    rows = attach_item_names([
        {'item_id': 'uuid-medpen'},
        {'item_id': 'uuid-ammo'},
    ])
    assert rows[0]['item_name'] == 'MedPen'
    assert rows[0]['item_name_zh'] == '醫療筆'
    assert rows[1]['item_name'] == 'Ammo Box'
    assert rows[1]['item_name_zh'] is None


def test_unknown_item_falls_back_to_uuid(seed_items):
    """主檔還沒同步、或物品已從 API 消失時，前端至少要有東西可顯示。"""
    rows = attach_item_names([{'item_id': 'uuid-not-synced-yet'}])
    assert rows[0]['item_name'] == 'uuid-not-synced-yet'
    assert rows[0]['item_name_zh'] is None


def test_row_without_item_id_does_not_crash(seed_items):
    rows = attach_item_names([{'note': '盤點調整'}])
    assert rows[0]['item_name'] is None


def test_both_history_endpoints_return_the_same_shape(
        client, auth_headers, seed_items):
    """後台與玩家自助兩支 /history 的物品欄位必須一致 —— 之前 inventory 版
    少了 item_name_zh，前端得為兩支各寫一套處理。"""
    from src import WMS_SCOPE_ID
    from src.models.inventory import OWNER_PLAYER, Inventory
    from src.models.player import Player

    Player.create(player_name='Tom', star_citizen_id='Tom_SC', password='hunter22')
    Inventory.adjust(WMS_SCOPE_ID, OWNER_PLAYER, 'Tom_SC', 'Stanton',
                     '', 'uuid-medpen', 3, actor='Tom')

    admin_rows = client.get('/inventory/history',
                            headers=auth_headers).get_json()['data']

    token = client.post('/player/login', json={
        'star_citizen_id': 'Tom_SC', 'password': 'hunter22'}).get_json()['token']
    player_rows = client.get('/player/inventory/history',
                             headers={'Authorization': f'Bearer {token}'}).get_json()['data']

    assert admin_rows and player_rows
    for rows in (admin_rows, player_rows):
        assert rows[0]['item_name'] == 'MedPen'
        assert rows[0]['item_name_zh'] == '醫療筆'
