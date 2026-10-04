"""scripts/seed_demo_holdings.py：建立、重跑、清除都只動到測試資料。"""
from scripts import seed_demo_holdings as seed
from src.mongo import get_db


def _masters():
    db = get_db()
    db['vehicle_master'].insert_many([
        {'_id': f'v{i}', 'name': f'Ship {i}', 'name_lower': f'ship {i}', 'is_current': True, 'is_spaceship': True}
        for i in range(4)])
    db['blueprint_master'].insert_many([
        {'_id': f'b{i}', 'name': f'Blueprint {i}', 'name_lower': f'blueprint {i}', 'is_current': True}
        for i in range(4)])
    db['item_master'].insert_many([
        {'_id': f'i{i}', 'name': f'Item {i}', 'name_lower': f'item {i}', 'is_current': True} for i in range(3)])
    db['players'].insert_one({'star_citizen_id': 'RealPlayer', 'nickname': '真的玩家', 'deleted_at': None})


def test_seed_and_remove(app):
    _masters()
    seed.remove()
    created = seed.seed()
    assert created['players'] == 3 and created['fleet'] == 7 and created['blueprints'] == 7
    db = get_db()
    assert db['fleet'].count_documents({}) == 7
    first = db['fleet'].find_one({'loadout_links.0': {'$exists': True}})
    assert first['loadout_links'][0]['url'] == 'https://erkul.games/s/abcd1234'
    assert db['inventory'].count_documents({'owner_type': 'guild', 'container': seed.GUILD_CONTAINER}) == 1

    # 重跑：先清再建，不會越疊越多
    seed.remove()
    seed.seed()
    assert db['players'].count_documents({'star_citizen_id': {'$regex': '^TEST_'}}) == 3
    assert db['fleet'].count_documents({}) == 7

    removed = seed.remove()
    assert removed['players'] == 3
    assert db['fleet'].count_documents({}) == 0 and db['blueprints'].count_documents({}) == 0
    assert db['inventory'].count_documents({}) == 0 and db['inventory_log'].count_documents({}) == 0
    assert db['players'].count_documents({}) == 1, '真的玩家不能被刪'
