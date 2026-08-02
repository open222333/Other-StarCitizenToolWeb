"""庫存邏輯測試（src/models/inventory.py）。

用 conftest.py 的 mongomock，不需要真實 MongoDB。
這裡測的是 Web API 與 Discord bot 共用的那一份邏輯。
"""
import pytest

from src.models.inventory import (OWNER_GUILD, OWNER_PLAYER, Inventory, InventoryLog,
                                  DiscordBinding, StockError, uscu_to_scu)
from src.mongo import get_db

SCOPE = 'test-scope'
ACTOR = 'TomLi'
ACTOR_ID = 'discord:111'

# Agricium 1 SCU、小零件 0.024 SCU、無體積資料
ITEM_BIG = {'_id': 'item-big', 'name': 'Agricium', 'name_lower': 'agricium',
            'type': 'Commodity', 'volume_uscu': 1_000_000, 'is_current': True, 'size': 1}
ITEM_SMALL = {'_id': 'item-small', 'name': 'Bracer Cooler', 'name_lower': 'bracer cooler',
              'type': 'Cooler', 'volume_uscu': 24_000, 'is_current': True, 'size': 1}
ITEM_RETIRED = {'_id': 'item-old', 'name': 'Removed Widget', 'name_lower': 'removed widget',
                'type': 'Cooler', 'volume_uscu': 50_000, 'is_current': False}
ITEM_NO_VOLUME = {'_id': 'item-novol', 'name': 'Mystery Crate',
                  'name_lower': 'mystery crate', 'type': 'Misc',
                  'volume_uscu': None, 'is_current': True}


@pytest.fixture
def seed_items():
    get_db()['item_master'].insert_many(
        [dict(ITEM_BIG), dict(ITEM_SMALL), dict(ITEM_RETIRED), dict(ITEM_NO_VOLUME)])


def add(item_id, qty, location, container=None,
        owner_type=OWNER_GUILD, player=None):
    return Inventory.adjust(SCOPE, owner_type, player, location, container,
                            item_id, qty, ACTOR, ACTOR_ID)


# ─────────────────────────────────────────────────────────── 單位換算

def test_uscu_to_scu():
    assert uscu_to_scu(1_000_000) == 1.0
    assert uscu_to_scu(24_000) == 0.024
    assert uscu_to_scu(None) == 0
    assert uscu_to_scu(0) == 0


# ─────────────────────────────────────────────────────────── 歸屬隔離

def test_guild_scope_ignores_player_argument():
    """公會庫一律強制 player=None，誤傳 handle 也撈不到別人的個人庫。"""
    from src.models.inventory import _owner_filter

    assert _owner_filter(SCOPE, OWNER_GUILD, None)['player'] is None
    assert _owner_filter(SCOPE, OWNER_GUILD, 'SomeoneElse')['player'] is None
    assert _owner_filter(SCOPE, OWNER_PLAYER, ACTOR)['player'] == ACTOR


def test_invalid_owner_type_rejected():
    with pytest.raises(StockError):
        Inventory.capacity(SCOPE, 'nonsense', None)


def test_guild_and_personal_are_isolated(seed_items):
    add(ITEM_BIG['_id'], 10, 'Area18')
    add(ITEM_BIG['_id'], 7, 'Area18', owner_type=OWNER_PLAYER, player=ACTOR)

    _, guild_total = Inventory.list_stock(SCOPE, OWNER_GUILD, None)
    _, player_total = Inventory.list_stock(SCOPE, OWNER_PLAYER, ACTOR)
    assert guild_total == 1 and player_total == 1

    assert Inventory.capacity(SCOPE, OWNER_GUILD, None)['units'] == 10
    assert Inventory.capacity(SCOPE, OWNER_PLAYER, ACTOR)['units'] == 7


# ─────────────────────────────────────────────────────────── 入庫

def test_add_accumulates_same_slot(seed_items):
    assert add(ITEM_BIG['_id'], 10, 'Area18')['quantity'] == 10
    assert add(ITEM_BIG['_id'], 5, 'Area18')['quantity'] == 15
    assert get_db()['inventory'].count_documents({}) == 1, '同儲位要累加，不是新增一筆'


def test_containers_are_separate_slots(seed_items):
    add(ITEM_BIG['_id'], 10, 'Area18')
    assert add(ITEM_BIG['_id'], 3, 'Area18', container='Box A')['quantity'] == 3
    assert get_db()['inventory'].count_documents({}) == 2


def test_add_rejects_zero_and_blank_location(seed_items):
    with pytest.raises(StockError):
        add(ITEM_BIG['_id'], 0, 'Area18')
    with pytest.raises(StockError):
        add(ITEM_BIG['_id'], 5, '   ')


# ─────────────────────────────────────────────────────────── 出庫

def test_remove_reduces_quantity(seed_items):
    add(ITEM_BIG['_id'], 10, 'Area18')
    assert add(ITEM_BIG['_id'], -4, 'Area18')['quantity'] == 6


def test_remove_over_stock_blocked_and_unchanged(seed_items):
    add(ITEM_BIG['_id'], 10, 'Area18')

    with pytest.raises(StockError, match='庫存不足'):
        add(ITEM_BIG['_id'], -100, 'Area18')

    doc = get_db()['inventory'].find_one({'item_id': ITEM_BIG['_id']})
    assert doc['quantity'] == 10, '被拒絕的出庫不該影響庫存'


def test_remove_nonexistent_slot_blocked(seed_items):
    with pytest.raises(StockError):
        add(ITEM_SMALL['_id'], -1, 'Area18')
    assert get_db()['inventory'].count_documents({'item_id': ITEM_SMALL['_id']}) == 0


def test_zero_quantity_slots_hidden(seed_items):
    add(ITEM_BIG['_id'], 3, 'Lorville')
    add(ITEM_BIG['_id'], -3, 'Lorville')

    _, total = Inventory.list_stock(SCOPE, OWNER_GUILD, None, location='Lorville')
    assert total == 0, '數量 0 的儲位不該列出來'


# ─────────────────────────────────────────────────────────── 移庫

def test_move_conserves_total(seed_items):
    add(ITEM_BIG['_id'], 20, 'Area18')

    result = Inventory.move(SCOPE, OWNER_GUILD, None, ITEM_BIG['_id'], 8,
                            'Area18', None, 'Lorville', 'Hangar 3', ACTOR, ACTOR_ID)
    assert result['src']['quantity'] == 12
    assert result['dst']['quantity'] == 8

    rows = list(get_db()['inventory'].find({'item_id': ITEM_BIG['_id']}))
    assert sum(r['quantity'] for r in rows) == 20, '移庫不該改變總量'


def test_move_over_stock_blocked_and_unchanged(seed_items):
    add(ITEM_BIG['_id'], 20, 'Area18')

    with pytest.raises(StockError, match='不足'):
        Inventory.move(SCOPE, OWNER_GUILD, None, ITEM_BIG['_id'], 999,
                       'Area18', None, 'Lorville', None, ACTOR, ACTOR_ID)

    rows = list(get_db()['inventory'].find({'item_id': ITEM_BIG['_id']}))
    assert sum(r['quantity'] for r in rows) == 20, '失敗的移庫不該留半套資料'


def test_move_same_location_rejected(seed_items):
    add(ITEM_BIG['_id'], 5, 'Area18')

    with pytest.raises(StockError, match='同一個位置'):
        Inventory.move(SCOPE, OWNER_GUILD, None, ITEM_BIG['_id'], 1,
                       'Area18', None, 'Area18', None, ACTOR, ACTOR_ID)


def test_move_rejects_non_positive(seed_items):
    add(ITEM_BIG['_id'], 5, 'Area18')
    with pytest.raises(StockError):
        Inventory.move(SCOPE, OWNER_GUILD, None, ITEM_BIG['_id'], 0,
                       'Area18', None, 'Lorville', None, ACTOR, ACTOR_ID)


# ─────────────────────────────────────────────────────────── 容量計算

def test_capacity_sums_scu_and_flags_unknown(seed_items):
    add(ITEM_BIG['_id'], 10, 'Area18')        # 10 SCU
    add(ITEM_SMALL['_id'], 100, 'Area18')     # 2.4 SCU
    add(ITEM_NO_VOLUME['_id'], 5, 'Area18')   # 無體積資料

    cap = Inventory.capacity(SCOPE, OWNER_GUILD, None, location='Area18')
    assert cap['total_scu'] == 12.4
    assert cap['units'] == 115
    assert cap['lines'] == 3
    assert cap['unknown_volume'] == 1, '缺體積的品項要算出來，否則總量低估卻無提示'


def test_capacity_all_locations(seed_items):
    add(ITEM_BIG['_id'], 10, 'Area18')
    add(ITEM_BIG['_id'], 3, 'Lorville')

    assert Inventory.capacity(SCOPE, OWNER_GUILD, None)['total_scu'] == 13.0


def test_capacity_empty_returns_zeros():
    cap = Inventory.capacity(SCOPE, OWNER_GUILD, None)
    assert cap == {'total_scu': 0.0, 'units': 0, 'lines': 0, 'unknown_volume': 0}


# ─────────────────────────────────────────────────────────── 已下架物品

def test_retired_item_still_queryable_and_flagged(seed_items):
    add(ITEM_RETIRED['_id'], 3, 'Area18')

    rows, total = Inventory.list_stock(SCOPE, OWNER_GUILD, None)
    assert total == 1
    assert rows[0]['item_retired'] is True, '遊戲已移除的物品要標記出來'
    assert rows[0]['quantity'] == 3, '主檔 is_current=False 不該讓庫存消失'


# ─────────────────────────────────────────────────────────── 查詢

def test_list_stock_joins_item_master(seed_items):
    add(ITEM_SMALL['_id'], 100, 'Area18')

    rows, _ = Inventory.list_stock(SCOPE, OWNER_GUILD, None)
    assert rows[0]['item_name'] == 'Bracer Cooler'
    assert rows[0]['total_uscu'] == 2_400_000
    assert rows[0]['total_scu'] == 2.4


def test_list_stock_survives_missing_item_master():
    """主檔沒這筆（同步還沒跑）時要退回顯示 item_id，不能整個查詢爆掉。"""
    add('ghost-uuid', 5, 'Area18')

    rows, total = Inventory.list_stock(SCOPE, OWNER_GUILD, None)
    assert total == 1
    assert rows[0]['item_name'] == 'ghost-uuid'
    assert rows[0]['total_uscu'] == 0


def test_find_item_locations_spans_owners(seed_items):
    add(ITEM_BIG['_id'], 10, 'Area18')
    add(ITEM_BIG['_id'], 4, 'Area18', container='Box A')
    add(ITEM_BIG['_id'], 7, 'Lorville', owner_type=OWNER_PLAYER, player=ACTOR)

    rows = Inventory.find_item_locations(SCOPE, ITEM_BIG['_id'])
    assert len(rows) == 3
    assert sum(r['quantity'] for r in rows) == 21
    assert {r['owner_type'] for r in rows} == {OWNER_GUILD, OWNER_PLAYER}


def test_distinct_locations(seed_items):
    add(ITEM_BIG['_id'], 1, 'Area18')
    add(ITEM_BIG['_id'], 1, 'Lorville')
    add(ITEM_SMALL['_id'], 1, 'Area18')

    assert Inventory.distinct_locations(SCOPE) == ['Area18', 'Lorville']


# ─────────────────────────────────────────────────────────── 稽核日誌

def test_every_change_is_logged(seed_items):
    add(ITEM_BIG['_id'], 10, 'Area18')
    add(ITEM_BIG['_id'], -3, 'Area18')
    Inventory.move(SCOPE, OWNER_GUILD, None, ITEM_BIG['_id'], 2,
                   'Area18', None, 'Lorville', None, ACTOR, ACTOR_ID)

    rows = InventoryLog.recent(SCOPE, limit=10)
    assert len(rows) == 3
    assert {r['action'] for r in rows} == {'add', 'remove', 'move'}
    for row in rows:
        assert row['actor'] == ACTOR
        assert row['actor_id'] == ACTOR_ID
        assert 'quantity_after' in row


def test_failed_change_is_not_logged(seed_items):
    add(ITEM_BIG['_id'], 5, 'Area18')
    with pytest.raises(StockError):
        add(ITEM_BIG['_id'], -99, 'Area18')

    rows = InventoryLog.recent(SCOPE, limit=10)
    assert len(rows) == 1, '被拒絕的異動不該留下日誌'


# ─────────────────────────────────────────────────────────── Discord 綁定

def test_binding_lifecycle():
    assert DiscordBinding.get('111') is None
    with pytest.raises(StockError, match='bind'):
        DiscordBinding.require_handle('111')

    DiscordBinding.bind('111', ACTOR, SCOPE)
    assert DiscordBinding.require_handle('111') == ACTOR

    # 重複綁定是更新，不會產生第二筆
    DiscordBinding.bind('111', 'TomLi2', SCOPE)
    assert get_db()['discord_bindings'].count_documents({'discord_id': '111'}) == 1
    assert DiscordBinding.require_handle('111') == 'TomLi2'

    assert DiscordBinding.unbind('111') is True
    assert DiscordBinding.unbind('111') is False


def test_binding_rejects_bad_handle():
    with pytest.raises(StockError):
        DiscordBinding.bind('111', 'x', SCOPE)
    with pytest.raises(StockError):
        DiscordBinding.bind('111', 'y' * 61, SCOPE)
