"""任務／勢力資料庫：映射（含中文匹配）、本地反查藍圖、API、同步明細合併。

上游資料形狀取自 2026-10 實際打 Star Citizen Wiki API 的回應：
`/missions?include=blueprints`（列表就帶獎勵藍圖池）、`/factions`（列表欄位少）
與 `/factions/<uuid>`（說明、總部、聲望階級…）。
"""
from datetime import datetime

import pytest

from src import sc_zh as Z
from src.models.mission import Faction, Mission
from src.mongo import get_db
from src.scdata import WIKI_DETAIL_RESOURCES, WIKI_QUERY_EXTRA, map_faction, map_mission

BP_HELMET = '850ad61b-2bd1-4c0c-be77-84a7133ce899'
BP_RIFLE = 'e3097998-28ef-4b3c-9f5e-7a1c2b3d4e5f'

MISSION_ROW = {
    'uuid': '091ffb61-7733-4ebe-8cef-66ec15de2320',
    'title': 'A Batch from Scratch',
    'description': ("Normally, I like to cook everything from scratch myself. Pride in product and all.\n\n"
                    "1. PROCESSING - Take the raw material from  [Pickup1|Address] to [Pickup2|Address]\n\n-Wallace"),
    'mission_giver': 'Wallace Klim',
    'debug_name': 'PU_Delivery_Local_DrugProduction_Stanton4_KlimIntro',
    'faction': {'name': 'Wallace Klim', 'uuid': 'c088786f-db63-4598-9c1b-a71ff4831f79',
                'link': 'https://api.star-citizen.wiki/api/factions/c088786f-db63-4598-9c1b-a71ff4831f79'},
    'illegal': True, 'legality_label': 'Illegal', 'shareable': True, 'once_only': True,
    'has_combat': False, 'reward_min': 20000, 'reward_max': 0, 'reward_currency': 'UEC',
    'star_systems': [], 'has_blueprints': True, 'has_hauling': True,
    'reputation_gained': [{'faction': 'Wallace Klim',
                           'faction_uuid': 'c088786f-db63-4598-9c1b-a71ff4831f79',
                           'scope': 'Affinity', 'tier': '+T_05', 'amount': 1000}],
    'cooldown_seconds': 60, 'cooldown_label': '60 seconds', 'reward_scope': 'Hauling',
    'game_version': '4.10.1-LIVE.12660092',
    'blueprints': [{
        'drop_chance': 1, 'drop_chance_percent': 100,
        'pool_uuid': '67a07f1a-ca8c-400d-984a-6088ecd3b482',
        'items': [
            {'name': 'Badami Helmet', 'uuid': '305c8b36-61a3-4065-b514-199719de9ac0',
             'blueprint_link': f'https://api.star-citizen.wiki/api/blueprints/{BP_HELMET}'},
            {'name': 'Killshot Rifle', 'uuid': 'c098e722-902a-435b-83f8-a96cec36a012',
             'blueprint_link': f'https://api.star-citizen.wiki/api/blueprints/{BP_RIFLE}'},
        ],
    }],
}

FACTION_ROW = {
    'uuid': '569f1e53-a971-462b-abe3-969a8e096ff5', 'name': 'Adagio Holdings',
    'faction_type': 'Lawful', 'lawful': True, 'is_npc': False, 'has_reputation': True,
    'description': 'Founded by retired Naval logistics personnel…', 'headquarters': 'Keene, Killian System',
    'focus': 'Salvaging', 'reputation_ladder': [{'name': 'Applicant', 'min_reputation': 0}],
}


def test_wiki_config_for_missions_and_factions():
    assert WIKI_QUERY_EXTRA['missions'] == {'include': 'blueprints'}
    assert 'factions' in WIKI_DETAIL_RESOURCES


# ═══════════════════════════════════════════════════════════
#  中文匹配
# ═══════════════════════════════════════════════════════════

def test_clean_helpers():
    assert Z.clean_title_zh('需要戰術打擊小組 <EM4>[300 聲望] [藍圖]</EM4>') == '需要戰術打擊小組'
    assert Z.clean_text_zh('一\\n\\n到 ~mission(Location|Address) <EM4>注意</EM4>') == '一\n\n到 [Location] 注意'
    assert Z.clean_mission_text('從 [Pickup1|Address] 到 [DropOff1|Address]') == '從 [Pickup1] 到 [DropOff1]'


def test_map_mission_matches_title_and_description(seed_translations):
    seed_translations({
        'mg_klim_localdelivery_drugprod_title_intro': ('A Batch from Scratch', '從零開始的一批 <EM4>[藍圖]</EM4>'),
        'mg_klim_localdelivery_drugprod_desc_intro': (
            'Normally, I like to cook everything from scratch myself. Pride in product and all.'
            '\n\n~mission(Itinerary)\n\n-Wallace',
            '通常情況下，我喜歡親手製作。\\n\\n~mission(Itinerary)\\n\\n-華萊士'),
        'MissionGivers_WallaceKlim': ('Wallace Klim', '華萊士·克里姆'),
        'WallaceKlim_RepUI_Name': ('Wallace Klim', '華萊士·克里姆'),
    })
    doc = map_mission(MISSION_ROW)
    assert doc['title_zh'] == '從零開始的一批'
    assert doc['title_key'] == 'mg_klim_localdelivery_drugprod_title_intro'
    assert doc['description_zh'] == '通常情況下，我喜歡親手製作。\n\n[Itinerary]\n\n-華萊士'
    assert '[Pickup1]' in doc['description'] and '|Address' not in doc['description']
    assert doc['mission_giver_zh'] == '華萊士·克里姆'
    assert doc['faction_name_zh'] == '華萊士·克里姆'
    assert doc['blueprint_uuids'] == [BP_HELMET, BP_RIFLE]
    assert doc['blueprint_pools'][0]['drop_chance'] == 1
    assert doc['illegal'] is True and doc['reward_scope'] == 'Hauling'


def test_same_title_picks_key_whose_description_matches(seed_translations):
    """兩個任務英文標題一樣、翻譯不同：用說明對上的那個，說明也一起翻。"""
    seed_translations({
        'rain_collect_a_name_01': ('Additional Resources For Research', '研究用額外資源'),
        'rain_collect_a_desc_01': ('We need quartz samples for the lab.', '我們需要石英樣本。'),
        'rain_collect_b_name_01': ('Additional Resources For Research', '更多資源供研究'),
        'rain_collect_b_desc_01': ('Bring us some scrap metal from the debris field.', '帶廢金屬回來。'),
    })
    got = Z.mission_text_zh('Additional Resources For Research',
                            'Bring us some scrap metal from the debris field, quickly.')
    assert got['title_zh'] == '更多資源供研究'
    assert got['description_zh'] == '帶廢金屬回來。'
    # 說明對不上任何一個：標題用優先的那個，說明不硬配
    got = Z.mission_text_zh('Additional Resources For Research', 'Something completely different here.')
    assert got['title_zh'] in ('研究用額外資源', '更多資源供研究')
    assert got['description_zh'] is None


def test_mission_without_translation():
    doc = map_mission({**MISSION_ROW, 'title': 'Nothing Like This', 'mission_giver': '', 'faction': None})
    assert doc['title_zh'] is None and doc['description_zh'] is None
    assert doc['faction_uuid'] is None and doc['mission_giver_zh'] is None


def test_map_faction_uses_repui_family(seed_translations):
    seed_translations({
        'Adagio_RepUI_DisplayName': ('Adagio Holdings', '阿德吉奧集團'),
        'Adagio_RepUI_Description': ('Founded by retired Naval logistics personnel…', '由退役海軍後勤人員創立…'),
        'Adagio_RepUI_HQ': ('Keene, Killian System', '奇林星系 基恩'),
        'Adagio_RepUI_Focus': ('Salvaging', '打撈'),
    })
    doc = map_faction(FACTION_ROW)
    assert doc['name_zh'] == '阿德吉奧集團'
    assert doc['description_zh'] == '由退役海軍後勤人員創立…'
    assert doc['headquarters_zh'] == '奇林星系 基恩'
    assert doc['focus_zh'] == '打撈'
    assert doc['leadership_zh'] is None
    assert doc['reputation_ladder'] == FACTION_ROW['reputation_ladder']


def test_mappers_reject_missing_uuid():
    assert map_mission({}) is None
    assert map_faction({'name': 'x'}) is None


# ═══════════════════════════════════════════════════════════
#  本地反查
# ═══════════════════════════════════════════════════════════

def _insert_mission(_id, title, *, pools=None, faction_uuid='f1', has_bp=None, **extra):
    pools = pools or []
    uuids = []
    for p in pools:
        for it in p['items']:
            if it['blueprint_uuid'] not in uuids:
                uuids.append(it['blueprint_uuid'])
    get_db()['mission_master'].insert_one({
        '_id': _id, 'title': title, 'title_lower': title.lower(), 'title_zh': extra.pop('title_zh', None),
        'faction_uuid': faction_uuid, 'faction_name': extra.pop('faction_name', 'Faction One'),
        'reward_scope': extra.pop('reward_scope', 'Hauling'), 'illegal': extra.pop('illegal', False),
        'star_systems': extra.pop('star_systems', ['Stanton']),
        'has_blueprints': bool(uuids) if has_bp is None else has_bp,
        'blueprint_pools': pools, 'blueprint_uuids': uuids,
        'is_current': extra.pop('is_current', True), 'raw': {'x': 1}, **extra,
    })


def _pool(chance, *bp_uuids):
    return {'pool_uuid': f'p-{chance}', 'drop_chance': chance,
            'items': [{'name': u, 'blueprint_uuid': u} for u in bp_uuids]}


@pytest.fixture
def missions(app):
    _insert_mission('m1', 'Alpha Job', pools=[_pool(1, 'bp-a')], title_zh='甲任務')
    _insert_mission('m2', 'Beta Job', pools=[_pool(0.35, 'bp-a', 'bp-b')], illegal=True,
                    reward_scope='Assassination', star_systems=['Pyro'], faction_uuid='f2',
                    faction_name='Faction Two')
    _insert_mission('m3', 'Gamma Job')
    _insert_mission('m-old', 'Retired Job', pools=[_pool(1, 'bp-a')], is_current=False)


def test_for_blueprint_sorted_by_chance(missions):
    rows = Mission.for_blueprint('bp-a')
    assert [(r['_id'], r['chance'], r['pool_size']) for r in rows] == [('m1', 1, 1), ('m2', 0.35, 2)]
    assert 'blueprint_pools' not in rows[0] and 'raw' not in rows[0]
    assert Mission.for_blueprint('nope') == []


def test_counts_for_blueprints(missions):
    assert Mission.counts_for_blueprints(['bp-a', 'bp-b', 'bp-c']) == {'bp-a': 2, 'bp-b': 1}
    assert sorted(Mission.blueprint_uuids_with_missions()) == ['bp-a', 'bp-b']


def test_list_filters(missions):
    assert Mission.list_all()[1] == 3
    assert [r['_id'] for r in Mission.list_all(legality=['illegal'])[0]] == ['m2']
    assert Mission.list_all(legality=['legal', 'illegal'])[1] == 3
    assert [r['_id'] for r in Mission.list_all(reward_scopes=['Assassination', 'Bounty'])[0]] == ['m2']
    assert [r['_id'] for r in Mission.list_all(star_systems=['Pyro'])[0]] == ['m2']
    assert [r['_id'] for r in Mission.list_all(has_blueprints=True)[0]] == ['m1', 'm2']
    assert [r['_id'] for r in Mission.list_all(missing_zh=True)[0]] == ['m2', 'm3']
    assert [r['_id'] for r in Mission.list_all(query='甲')[0]] == ['m1']
    assert [r['_id'] for r in Mission.list_all(blueprint_uuid='bp-b')[0]] == ['m2']
    assert [r['_id'] for r in Mission.list_all(mission_id='m3')[0]] == ['m3']
    assert 'raw' not in Mission.list_all()[0][0]


def test_faction_counts(missions):
    get_db()['faction_master'].insert_many([
        {'_id': 'f1', 'name': 'Faction One', 'name_lower': 'faction one', 'is_current': True, 'raw': {}},
        {'_id': 'f2', 'name': 'Faction Two', 'name_lower': 'faction two', 'is_current': True},
        {'_id': 'f3', 'name': 'Quiet', 'name_lower': 'quiet', 'is_current': True},
    ])
    rows = {r['_id']: r for r in Faction.list_all()}
    assert (rows['f1']['mission_count'], rows['f1']['blueprint_mission_count']) == (2, 1)
    assert (rows['f3']['mission_count'], rows['f3']['blueprint_mission_count']) == (0, 0)
    assert 'raw' not in rows['f1']
    doc = Faction.get('f1')
    assert [m['_id'] for m in doc['missions']] == ['m1', 'm3']
    assert doc['missions'][0]['blueprint_count'] == 1


# ═══════════════════════════════════════════════════════════
#  API
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def player_headers(client):
    client.post('/player/register', json={
        'nickname': 'MissionPilot', 'star_citizen_id': 'MissionPilot', 'password': 'player-pw-123'})
    login = client.post('/player/login', json={
        'star_citizen_id': 'MissionPilot', 'password': 'player-pw-123'})
    return {'Authorization': f"Bearer {login.get_json()['token']}"}


def test_mission_endpoints(client, auth_headers, missions):
    body = client.get('/mission/?legality=illegal&reward_scope=Assassination', headers=auth_headers).get_json()
    assert body['total'] == 1 and body['data'][0]['_id'] == 'm2'
    facets = client.get('/mission/facets', headers=auth_headers).get_json()['data']
    assert facets['reward_scopes'] == ['Assassination', 'Hauling']
    assert facets['star_systems'] == ['Pyro', 'Stanton']
    assert [(f['uuid'], f['count']) for f in facets['factions']] == [('f1', 2), ('f2', 1)]
    assert client.get('/mission/m1', headers=auth_headers).get_json()['data']['title'] == 'Alpha Job'
    assert client.get('/mission/nope', headers=auth_headers).status_code == 404
    assert client.get('/mission/factions/nope', headers=auth_headers).status_code == 404


def test_player_can_see_missions_for_blueprint(client, player_headers, missions):
    resp = client.get('/mission/for-blueprint/bp-a', headers=player_headers)
    assert resp.status_code == 200
    assert [r['_id'] for r in resp.get_json()['data']] == ['m1', 'm2']
    assert client.get('/mission/for-blueprint/bp-a').status_code == 401


def test_blueprint_master_list_has_mission_count(client, auth_headers, missions):
    db = get_db()
    for uid, name in (('bp-a', 'Alpha Gun'), ('bp-b', 'Beta Gun'), ('bp-c', 'Gamma Gun')):
        db['blueprint_master'].insert_one({'_id': uid, 'name': name, 'name_lower': name.lower(),
                                           'is_current': True})
    body = client.get('/blueprint/master', headers=auth_headers).get_json()
    assert {r['_id']: r['mission_count'] for r in body['data']} == {'bp-a': 2, 'bp-b': 1, 'bp-c': 0}
    body = client.get('/blueprint/master?has_missions=1', headers=auth_headers).get_json()
    assert sorted(r['_id'] for r in body['data']) == ['bp-a', 'bp-b']


# ═══════════════════════════════════════════════════════════
#  同步：勢力逐筆補明細
# ═══════════════════════════════════════════════════════════

def test_faction_sync_merges_detail(monkeypatch):
    from tasks import scdata_sync

    monkeypatch.setattr(scdata_sync, 'SCDATA_REQUEST_DELAY', 0)
    monkeypatch.setattr(scdata_sync, 'wiki_rows', lambda client, resource: iter([
        {'uuid': 'f-1', 'name': 'Adagio Holdings', 'faction_type': 'Lawful'},
        {'uuid': 'f-2', 'name': 'Broken Detail'},
    ]))
    calls = []

    def fake_detail(client, resource, uuid):
        calls.append((resource, uuid))
        return {'uuid': uuid, 'description': 'Salvage people', 'focus': 'Salvaging'} if uuid == 'f-1' else None
    monkeypatch.setattr(scdata_sync, 'wiki_detail', fake_detail)

    result = scdata_sync._sync_wiki_resource(None, 'factions', 'run-1', datetime.utcnow())
    assert result['seen'] == 2 and calls == [('factions', 'f-1'), ('factions', 'f-2')]
    col = get_db()['faction_master']
    assert col.find_one({'_id': 'f-1'})['description'] == 'Salvage people'
    assert col.find_one({'_id': 'f-1'})['faction_type'] == 'Lawful'
    # 明細抓不到就用列表那筆
    assert col.find_one({'_id': 'f-2'})['name'] == 'Broken Detail'


def test_mission_sync_does_not_fetch_details(monkeypatch):
    from tasks import scdata_sync

    monkeypatch.setattr(scdata_sync, 'wiki_rows', lambda client, resource: iter([MISSION_ROW]))
    monkeypatch.setattr(scdata_sync, 'wiki_detail',
                        lambda *a: pytest.fail('任務不該逐筆抓明細（列表 include=blueprints 就有藍圖）'))
    scdata_sync._sync_wiki_resource(None, 'missions', 'run-1', datetime.utcnow())
    assert get_db()['mission_master'].find_one({'_id': MISSION_ROW['uuid']})['blueprint_uuids'] == [BP_HELMET, BP_RIFLE]


# ═══════════════════════════════════════════════════════════
#  獎勵藍圖的各種上游形狀
# ═══════════════════════════════════════════════════════════

def test_parse_flat_blueprint_list():
    """列表 include=blueprints 可能直接是一串藍圖物件（不是「池 → items」）。"""
    from src.scdata import parse_blueprint_pools
    pools, uuids = parse_blueprint_pools([
        {'uuid': 'bp-x', 'key': 'BP_CRAFT_X', 'name': 'X Rifle', 'drop_chance': 0.5},
        {'name': 'Y Helmet', 'link': 'https://api.star-citizen.wiki/api/blueprints/bp-y',
         'drop_chance_percent': 25},
    ])
    assert uuids == ['bp-x', 'bp-y']
    assert [p['drop_chance'] for p in pools] == [0.5, 0.25]


def test_parse_falls_back_to_output_item(app):
    """只有產出物品 uuid（或網頁 slug 連結）時，用藍圖主檔的 output_item_uuid 反查。"""
    from src.scdata import parse_blueprint_pools
    get_db()['blueprint_master'].insert_one({'_id': 'bp-helmet', 'output_item_uuid': 'item-helmet',
                                             'is_current': True})
    pools, uuids = parse_blueprint_pools([{'drop_chance': 1, 'items': [
        {'name': 'Badami Helmet', 'uuid': 'item-helmet',
         'item_link': 'https://api.star-citizen.wiki/api/items/item-helmet',
         'web_blueprint_link': 'https://api.star-citizen.wiki/blueprints/badami-helmet'},
        {'name': 'Unknown', 'uuid': 'item-nope', 'item_link': 'x'},
    ]}])
    assert uuids == ['bp-helmet']
    assert pools[0]['items'][0]['item_uuid'] == 'item-helmet'
    assert pools[0]['items'][1]['blueprint_uuid'] is None


def test_relink_after_blueprints_arrive(app):
    """任務先同步、藍圖後同步：藍圖同步完重新對應就補上。"""
    raw = {'blueprints': [{'drop_chance': 1, 'items': [
        {'name': 'Badami Helmet', 'uuid': 'item-helmet', 'item_link': 'x'}]}]}
    get_db()['mission_master'].insert_one({'_id': 'm-late', 'is_current': True, 'title': 'Late',
                                           'title_lower': 'late', 'blueprint_uuids': [],
                                           'blueprint_pools': [], 'raw': raw})
    assert Mission.relink_blueprints() == 0
    get_db()['blueprint_master'].insert_one({'_id': 'bp-helmet', 'output_item_uuid': 'item-helmet',
                                             'is_current': True})
    assert Mission.relink_blueprints() == 1
    assert Mission.counts_for_blueprints(['bp-helmet']) == {'bp-helmet': 1}


def test_parse_real_list_shape():
    """2026-10 實際 /missions?include=blueprints 的形狀：一串 {name, uuid(物品), link(藍圖 API)}，沒有機率。"""
    from src.scdata import parse_blueprint_pools
    pools, uuids = parse_blueprint_pools([
        {'name': 'Killshot Rifle', 'uuid': 'c098e722-902a-435b-83f8-a96cec36a012',
         'link': 'https://api.star-citizen.wiki/api/blueprints/e3097998-28ef-48ad-a220-2ddaa1a85ce3'},
        {'name': 'Deadrig Shotgun', 'uuid': '7b17e697-ad38-4999-87e4-14f5a6bee3ac',
         'link': 'https://api.star-citizen.wiki/api/blueprints/950e8099-037e-4d73-86fe-6266a08b02d1'},
    ])
    assert uuids == ['e3097998-28ef-48ad-a220-2ddaa1a85ce3', '950e8099-037e-4d73-86fe-6266a08b02d1']
    assert all(p['drop_chance'] is None for p in pools)


def test_refresh_translations_after_translation_sync(app, seed_translations):
    """任務先同步（當時沒有翻譯）→ 翻譯同步完重新比對，補上中文。"""
    from src.scdata import map_mission
    doc = map_mission(MISSION_ROW)
    assert doc['title_zh'] is None
    get_db()['mission_master'].insert_one(dict(doc, is_current=True))
    get_db()['faction_master'].insert_one({'_id': 'f-a', 'name': 'Adagio Holdings', 'is_current': True})
    seed_translations({
        'mg_klim_localdelivery_drugprod_title_intro': ('A Batch from Scratch', '從零開始的一批'),
        'MissionGivers_WallaceKlim': ('Wallace Klim', '華萊士·克里姆'),
        'Adagio_RepUI_DisplayName': ('Adagio Holdings', '阿德吉奧集團'),
    })
    from src.models import translation as T
    T.clear_cache()
    assert Mission.refresh_translations() == 1
    row = get_db()['mission_master'].find_one({'_id': MISSION_ROW['uuid']})
    assert row['title_zh'] == '從零開始的一批' and row['mission_giver_zh'] == '華萊士·克里姆'
    assert Mission.refresh_translations() == 0, '沒有變動就不寫'
    assert Faction.refresh_translations() == 1
    assert get_db()['faction_master'].find_one({'_id': 'f-a'})['name_zh'] == '阿德吉奧集團'


def test_title_matching_tolerates_tokens_quotes_and_filled_values(seed_translations):
    seed_translations({
        'cfp_blockade_title_001': ('CDF ALERT: ~mission(Location) Blockade Runners Needed',
                                   'CDF 警報：~mission(Location) 需要突破封鎖者'),
        'hh_crew_title_001': ("Crew Hasn’t Checked In", '船員還沒回報'),
        'delivery_title_001': ('Delivery for ~mission(Destination) Ready', '前往 ~mission(Destination) 的貨已備妥'),
        'generic_title_001': ('~mission(Title)', '萬用標題'),
    })
    # Wiki 用 [Location|Address] 寫代入欄位
    got = Z.mission_text_zh('CDF ALERT: [Location|Address] Blockade Runners Needed')
    assert got['title_zh'] == 'CDF 警報：[Location] 需要突破封鎖者'
    # 直引號 vs 彎引號、多餘空白
    assert Z.mission_text_zh("Crew  Hasn't Checked In")['title_zh'] == '船員還沒回報'
    # 已經填好值的標題：用樣板比對，把值帶進中文
    assert Z.mission_text_zh('Delivery for Lorville Ready')['title_zh'] == '前往 Lorville 的貨已備妥'
    # 整句都是代入欄位的樣板不能對到任何標題
    assert Z.mission_text_zh('Something Unrelated')['title_zh'] is None
