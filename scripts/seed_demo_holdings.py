"""本地開發用：建立幾筆「玩家持有」的測試資料（艦隊、藍圖、物品庫存），方便看玩家頁
「查詢」的蜂巢式下拉、後台「玩家擁有艦船」這些畫面。

⚠️ 只給本地／測試環境用，不要在正式環境跑（測試玩家會出現在大家的查詢結果裡）。

用法（在專案根目錄，api 容器裡跑）：
    docker compose exec api python -m scripts.seed_demo_holdings          # 建立（會先清掉舊的測試資料再重建）
    docker compose exec api python -m scripts.seed_demo_holdings --remove # 只清掉測試資料

測試資料怎麼認：
  - 玩家：遊戲ID 以 TEST_ 開頭（密碼都是 test-123456，存的是 bcrypt 雜湊）
  - 那些玩家名下的艦隊、藍圖、個人庫存，以及入出庫紀錄
  - 公會共享庫的測試庫存：容器欄位是「測試資料」
  清除時這些會直接刪掉（是測試資料，不走軟刪除）。

船、藍圖、物品從目前資料庫的主檔挑（要先同步過艦船／藍圖／物品），
地點優先用地點資料庫的「可存放」地點。配件網址用通用的假代碼。
"""

import argparse
import sys

from src import WMS_SCOPE_ID
from src.models.blueprint import Blueprint
from src.models.fleet import Fleet
from src.models.inventory import OWNER_GUILD, OWNER_PLAYER, Inventory, InventoryLog
from src.models.player import Player
from src.models.starmap import Starmap
from src.models.visibility import hidden_filter
from src.mongo import get_db

PREFIX = 'TEST_'
PASSWORD = 'test-123456'
GUILD_CONTAINER = '測試資料'

PLAYERS = [
    {'star_citizen_id': 'TEST_Pilot01', 'nickname': '測試飛行員A', 'player_name': 'Test Pilot A',
     'discord_name': 'test_pilot_a', 'discord_public': True},
    {'star_citizen_id': 'TEST_Pilot02', 'nickname': '測試飛行員B', 'player_name': 'Test Pilot B'},
    {'star_citizen_id': 'TEST_Pilot03', 'nickname': '測試飛行員C', 'player_name': 'Test Pilot C'},
]
FALLBACK_LOCATIONS = ['Area18', 'Lorville', 'New Babbage']


def _pick(collection: str, limit: int, extra: dict = None, sort_field: str = 'name') -> list:
    filt = {'is_current': True, 'name': {'$nin': [None, '']}, **hidden_filter(), **(extra or {})}
    return list(get_db()[collection].find(filt, {'name': 1}).sort(sort_field, 1).limit(limit))


def remove() -> dict:
    db = get_db()
    players = list(db['players'].find({'star_citizen_id': {'$regex': f'^{PREFIX}'}}, {'_id': 1, 'star_citizen_id': 1}))
    ids = [p['_id'] for p in players]
    scids = [p['star_citizen_id'] for p in players]
    out = {
        'fleet': db['fleet'].delete_many({'player_id': {'$in': ids}}).deleted_count,
        'blueprints': db[Blueprint.COLLECTION].delete_many({'player_id': {'$in': ids}}).deleted_count,
        'inventory': db[Inventory.COLLECTION].delete_many({'$or': [
            {'owner_type': OWNER_PLAYER, 'player': {'$in': scids}},
            {'owner_type': OWNER_GUILD, 'container': GUILD_CONTAINER},
        ]}).deleted_count,
        'inventory_log': db[InventoryLog.COLLECTION].delete_many({'$or': [
            {'actor_id': {'$in': [f'player:{s}' for s in scids]}},
            {'container': GUILD_CONTAINER},
        ]}).deleted_count,
        'players': db['players'].delete_many({'_id': {'$in': ids}}).deleted_count,
    }
    return out


def seed() -> dict:
    vehicles = _pick('vehicle_master', 4, {'is_spaceship': True})
    blueprints = _pick('blueprint_master', 4)
    items = _pick('item_master', 3)
    if not vehicles or not blueprints or not items:
        sys.exit('主檔是空的：請先到後台「資料同步排程」同步艦船、藍圖、物品再跑。')
    locations = [l['name'] for l in Starmap.storage_locations()[:3]] or FALLBACK_LOCATIONS
    while len(locations) < 3:
        locations.append(FALLBACK_LOCATIONS[len(locations)])

    created = {'players': 0, 'fleet': 0, 'blueprints': 0, 'inventory': 0}
    player_ids = []
    for spec in PLAYERS:
        pid = Player.create(password=PASSWORD, **spec)
        player_ids.append((pid, spec['star_citizen_id']))
        created['players'] += 1

    # 艦隊：三個人都有第一艘（看得出「同一艘船好幾個人有」），各自再多一兩艘；第一位填配件網址
    fleet_plan = [
        [(vehicles[0], 2), (vehicles[1], 1), (vehicles[2], 1)],
        [(vehicles[0], 1), (vehicles[-1], 1)],
        [(vehicles[0], 1), (vehicles[1], 3)],
    ]
    links = [
        [{'label': 'PvP', 'url': 'abcd1234'}, {'label': '採礦', 'url': 'efgh5678'}],
        [{'url': 'ijkl9012'}],
        [],
    ]
    for (pid, _), plan, my_links in zip(player_ids, fleet_plan, links):
        for vehicle, qty in plan:
            result = Fleet.bulk_create_for_player(pid, [{'uuid': vehicle['_id'], 'name': vehicle['name']}], quantity=qty)
            created['fleet'] += len(result['added'])
        if my_links:
            first = next(iter(Fleet.find_for_player(pid)), None)
            if first:
                Fleet.update_for_player(first['_id'], pid, loadout_links=my_links)

    # 藍圖：第一張大家都有，其他分散
    bp_plan = [blueprints[:3], blueprints[:1] + blueprints[3:4], blueprints[:2]]
    for (pid, _), plan in zip(player_ids, bp_plan):
        result = Blueprint.bulk_create_for_player(
            pid, [{'uuid': b['_id'], 'name': b['name']} for b in plan], acquisition_method='測試資料')
        created['blueprints'] += len(result['added'])

    # 物品：同一個物品放在不同人、不同地點；再放一筆在公會共享庫
    stock_plan = [
        (0, items[0], locations[0], 5), (0, items[0], locations[1], 2), (0, items[1], locations[0], 1),
        (1, items[0], locations[2], 3), (1, items[2], locations[1], 4),
        (2, items[1], locations[2], 6),
    ]
    for idx, item, location, qty in stock_plan:
        pid, scid = player_ids[idx]
        Inventory.adjust(WMS_SCOPE_ID, OWNER_PLAYER, scid, location=location, container=None,
                         item_id=item['_id'], delta=qty, actor=scid, actor_id=f'player:{scid}', note='測試資料')
        created['inventory'] += 1
    Inventory.adjust(WMS_SCOPE_ID, OWNER_GUILD, None, location=locations[0], container=GUILD_CONTAINER,
                     item_id=items[0]['_id'], delta=10, actor='seed', actor_id='seed', note='測試資料')
    created['inventory'] += 1
    return created


def main():
    parser = argparse.ArgumentParser(description='建立／清除玩家持有的測試資料（只給本地用）')
    parser.add_argument('--remove', action='store_true', help='只清掉測試資料，不重建')
    args = parser.parse_args()
    removed = remove()
    print('已清除舊的測試資料：', removed)
    if args.remove:
        return
    print('已建立：', seed())
    print(f'測試玩家：{", ".join(p["star_citizen_id"] for p in PLAYERS)}（密碼 {PASSWORD}）')


if __name__ == '__main__':
    main()
