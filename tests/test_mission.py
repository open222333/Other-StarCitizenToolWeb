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


def test_for_blueprint_lists_pool_blueprints(missions):
    """每個任務附上它會給的所有藍圖（跨所有獎勵池去重），玩家頁標出已登記／未登記。"""
    from src.mongo import get_db
    get_db()['blueprint_master'].insert_many([
        {'_id': 'bp-a', 'name': 'Gun A', 'name_zh': '槍 A', 'is_current': True},
        {'_id': 'bp-b', 'name': 'Gun B', 'is_current': True, 'is_available_by_default': True},
    ])
    rows = {r['_id']: r for r in Mission.for_blueprint('bp-a')}
    assert rows['m1']['pool_blueprints'] == [
        {'uuid': 'bp-a', 'name': 'Gun A', 'name_zh': '槍 A', 'is_available_by_default': False}]
    assert [b['uuid'] for b in rows['m2']['pool_blueprints']] == ['bp-a', 'bp-b']
    assert rows['m2']['pool_blueprints'][1]['is_available_by_default'] is True
    # 好幾個池：其他池的藍圖也要列（重複的只列一次）
    _insert_mission('m4', 'Delta Job', pools=[_pool(0.5, 'bp-a', 'bp-b'), _pool(0.2, 'bp-c', 'bp-a')])
    rows = {r['_id']: r for r in Mission.for_blueprint('bp-a')}
    assert [b['uuid'] for b in rows['m4']['pool_blueprints']] == ['bp-a', 'bp-b', 'bp-c']
    assert rows['m4']['pool_size'] == 2


def test_list_pool_items_mark_available_by_default(missions):
    """列表的獎勵池藍圖附上中文名稱與是否預設可用（玩家頁「任務」分頁算已登記／未登記用）。"""
    from src.mongo import get_db
    get_db()['blueprint_master'].insert_many([
        {'_id': 'bp-a', 'name': 'Gun A', 'name_zh': '槍 A', 'is_current': True},
        {'_id': 'bp-b', 'name': 'Gun B', 'is_current': True, 'is_available_by_default': True},
    ])
    row = Mission.list_all(mission_id='m2')[0][0]
    items = row['blueprint_pools'][0]['items']
    assert [(it['blueprint_uuid'], it['name_zh'], it['is_available_by_default']) for it in items] == [
        ('bp-a', '槍 A', False), ('bp-b', None, True)]


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


def test_list_sort_by_cooldown_and_reputation(missions):
    get_db()['mission_master'].update_one({'_id': 'm1'}, {'$set': {'cooldown_seconds': 600, 'reputation_gained': [{'amount': 50}]}})
    get_db()['mission_master'].update_one({'_id': 'm2'}, {'$set': {'cooldown_seconds': 60, 'reputation_gained': [{'amount': 900}]}})
    assert [r['_id'] for r in Mission.list_all(sort_by='cooldown', sort_dir='desc')[0]][:2] == ['m1', 'm2']
    assert [r['_id'] for r in Mission.list_all(sort_by='reputation', sort_dir='desc')[0]][:2] == ['m2', 'm1']


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


def test_faction_hides_invisible_missions_for_players(missions):
    get_db()['faction_master'].insert_one({'_id': 'f1', 'name': 'Faction One', 'name_lower': 'faction one', 'is_current': True})
    get_db()['mission_master'].update_one({'_id': 'm3'}, {'$set': {'player_visible': False}})
    assert [m['_id'] for m in Faction.get('f1')['missions']] == ['m1', 'm3']
    assert [m['_id'] for m in Faction.get('f1', visible_only=True)['missions']] == ['m1']
    rows = {r['_id']: r for r in Faction.list_all(visible_only=True)}
    assert rows['f1']['mission_count'] == 1


def test_faction_reputation_groups_missions_by_rank(missions):
    from src.models.mission import ladder_steps
    get_db()['faction_master'].insert_one({
        '_id': 'f1', 'name': 'Faction One', 'name_lower': 'faction one', 'is_current': True,
        'reputation_ladder': [{'name': 'Applicant', 'min_reputation': 0}, {'name': 'Junior', 'min_reputation': 1500}]})
    db = get_db()['mission_master']
    db.update_one({'_id': 'm1'}, {'$set': {'min_standing_name': 'junior'}})
    db.update_one({'_id': 'm3'}, {'$set': {'min_standing_name': 'PLACEHOLDER'}})
    _insert_mission('m5', 'Epsilon Job', min_standing_name='Veteran')
    data = Faction.reputation('f1')
    assert [(r['name'], r['min_reputation'], [m['_id'] for m in r['missions']]) for r in data['ranks']] == [
        ('Applicant', 0, []), ('Junior', 1500, ['m1'])]
    assert [m['_id'] for m in data['open']] == ['m3'], 'PLACEHOLDER 當作沒有門檻'
    assert [m['_id'] for m in data['unmatched']] == ['m5']
    assert data['ranks'][1]['missions'][0]['blueprint_pools'][0]['items'][0]['blueprint_uuid'] == 'bp-a'
    assert Faction.reputation('nope') is None
    assert Faction.ladders()['f1'][1] == {'name': 'Junior', 'min_reputation': 1500}
    assert ladder_steps({'ranks': ['A', {'display_name': 'B', 'threshold': 5}]}) == [
        {'name': 'A', 'min_reputation': None}, {'name': 'B', 'min_reputation': 5}]


def test_ladder_scopes_shapes():
    from src.models.mission import ladder_scopes, ladder_steps
    one = [{'name': 'Applicant', 'min_reputation': 0}]
    assert ladder_scopes(one) == [{'scope': None, 'steps': [{'name': 'Applicant', 'min_reputation': 0}]}]
    assert ladder_scopes({'standings': one}) == [{'scope': None, 'steps': [{'name': 'Applicant', 'min_reputation': 0}]}]
    multi = [{'scope': 'Affinity', 'ranks': [{'name': 'Neutral', 'min_reputation': 0}]},
             {'name': 'Hauling', 'standings': [{'name': 'Trainee', 'min': 0}, {'name': 'Rookie', 'min': 2000}]}]
    assert [(s['scope'], [x['name'] for x in s['steps']]) for s in ladder_scopes(multi)] == [
        ('Affinity', ['Neutral']), ('Hauling', ['Trainee', 'Rookie'])]
    by_key = {'Affinity': [{'name': 'Neutral', 'min_reputation': 0}], 'Hauling': {'ranks': ['Trainee']}}
    assert [s['scope'] for s in ladder_scopes(by_key)] == ['Affinity', 'Hauling']
    assert [x['name'] for x in ladder_steps(multi)] == ['Neutral', 'Trainee', 'Rookie']
    assert ladder_scopes(None) == [] and ladder_scopes({'x': 1}) == []


def test_faction_reputation_multiple_scopes(missions):
    """紅風物流這種：立場（Affinity）＋貨運（Hauling）兩條階級表，任務放到它給的那種聲望底下。"""
    db = get_db()
    db['faction_master'].insert_one({
        '_id': 'f1', 'name': 'Faction One', 'name_lower': 'faction one', 'is_current': True,
        'reputation_ladder': [
            {'scope': 'Affinity', 'ranks': [{'name': 'Neutral', 'min_reputation': 0}, {'name': 'Trusted', 'min_reputation': 500}]},
            {'scope': 'Hauling', 'ranks': [{'name': 'Trainee', 'min_reputation': 0}, {'name': 'Trusted', 'min_reputation': 900}]}]})
    rep = lambda sc: [{'faction': 'Faction One', 'faction_uuid': 'f1', 'scope': sc, 'amount': 100}]
    m = db['mission_master']
    m.update_one({'_id': 'm1'}, {'$set': {'min_standing_name': 'Trusted', 'reputation_gained': rep('Hauling')}})
    m.update_one({'_id': 'm2'}, {'$set': {'min_standing_name': 'trusted', 'reward_scope': 'Bounty', 'faction_uuid': 'f1',
                                          'reputation_gained': rep('Affinity')}})
    m.update_one({'_id': 'm3'}, {'$set': {'reputation_gained': rep('Salvage')}})
    data = Faction.reputation('f1')
    got = {s['scope']: [(r['name'], [x['_id'] for x in r['missions']]) for r in s['ranks']] for s in data['scopes']}
    assert got == {'Affinity': [('Neutral', []), ('Trusted', ['m2'])],
                   'Hauling': [('Trainee', []), ('Trusted', ['m1'])],
                   'Salvage': []}, '同名階級依任務給的聲望種類分開；階級表沒有的種類也列出來'
    assert data['ranks'] == data['scopes'][0]['ranks']
    row = next(r for r in Faction.list_all() if r['_id'] == 'f1')
    assert row['scopes'] == ['Affinity', 'Hauling', 'Salvage']
    assert 'Hauling' in row['mission_types'] and 'Bounty' in row['mission_types']


def test_faction_single_unnamed_ladder_takes_mission_scope(missions):
    db = get_db()
    db['faction_master'].insert_one({'_id': 'f1', 'name': 'Faction One', 'name_lower': 'faction one', 'is_current': True,
                                     'reputation_ladder': [{'name': 'Applicant', 'min_reputation': 0}]})
    db['mission_master'].update_many({}, {'$set': {'reputation_gained': [{'faction_uuid': 'f1', 'scope': 'Hauling', 'amount': 5}]}})
    assert [s['scope'] for s in Faction.reputation('f1')['scopes']] == ['Hauling']


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
    assert client.get('/mission/factions/nope/reputation', headers=auth_headers).status_code == 404
    assert client.get('/mission/factions/ladders', headers=auth_headers).get_json()['success']


def test_player_can_see_missions_for_blueprint(client, player_headers, missions):
    resp = client.get('/mission/for-blueprint/bp-a', headers=player_headers)
    assert resp.status_code == 200
    assert [r['_id'] for r in resp.get_json()['data']] == ['m1', 'm2']
    assert client.get('/mission/for-blueprint/bp-a').status_code == 200  # 不登入也能用（@public_api）


def test_player_cannot_see_hidden_mission_or_its_facets(client, player_headers, auth_headers, missions):
    get_db()['mission_master'].update_one({'_id': 'm2'}, {'$set': {'player_visible': False}})
    assert client.get('/mission/m2', headers=player_headers).status_code == 404
    assert client.get('/mission/m2', headers=auth_headers).status_code == 200, '後台看得到'
    facets = client.get('/mission/facets', headers=player_headers).get_json()['data']
    assert facets['reward_scopes'] == ['Hauling'] and facets['star_systems'] == ['Stanton']
    assert [(f['uuid'], f['count']) for f in facets['factions']] == [('f1', 2)]


def test_refinery_version_key_mixed_parts():
    from src.models.uex_refinery_method import _version_key
    # 數字段跟文字段混在一起不能出錯（原本會 TypeError）；純數字的照數字大小排
    assert sorted(['4.1a', '4.1.1', '4.10', '4.2'], key=_version_key)[:3] == ['4.1.1', '4.2', '4.10']


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
    """沒有前置條件的任務不抓明細（列表 include=blueprints 就有藍圖）。"""
    from tasks import scdata_sync

    monkeypatch.setattr(scdata_sync, 'wiki_rows', lambda client, resource: iter([MISSION_ROW]))
    monkeypatch.setattr(scdata_sync, 'wiki_detail',
                        lambda *a: pytest.fail('沒有前置條件的任務不該抓明細'))
    scdata_sync._sync_wiki_resource(None, 'missions', 'run-1', datetime.utcnow())
    doc = get_db()['mission_master'].find_one({'_id': MISSION_ROW['uuid']})
    assert doc['blueprint_uuids'] == [BP_HELMET, BP_RIFLE]
    assert doc['prerequisite_groups'] == [] and doc['prerequisite_uuids'] == []


PRE_A, PRE_B = '42d67dfb-6c76-498e-a9ca-1ff69b38be68', '8aa22824-56ad-4522-8e76-525e58cf9865'
PREREQ_DETAIL = {
    'uuid': MISSION_ROW['uuid'],
    # 明細的 blueprints 形狀跟列表不同，不能蓋掉列表那份
    'blueprints': [{'name': 'Detail Shape'}],
    'prerequisite_groups': [{'required_count': 2, 'required_tags': [], 'excluded_tags': [], 'missions': [
        {'uuid': PRE_A, 'title': 'Advanced Tracker License Certification', 'mission_type': 'Bounty Hunter',
         'link': f'https://api.star-citizen.wiki/api/missions/{PRE_A}'},
        {'uuid': PRE_B, 'title': 'Active Bounty Evaluation', 'mission_type': 'Bounty Hunter'},
    ]}],
    'unlock_groups': [],
}


def test_mission_sync_fetches_prerequisites_only(monkeypatch):
    """有前置條件的任務逐筆抓明細，但只合併 prerequisite_groups；明細抓失敗保留上次的。"""
    from tasks import scdata_sync

    monkeypatch.setattr(scdata_sync, 'SCDATA_REQUEST_DELAY', 0)
    row = {**MISSION_ROW, 'has_prerequisites': True}
    monkeypatch.setattr(scdata_sync, 'wiki_rows', lambda client, resource: iter([row]))
    monkeypatch.setattr(scdata_sync, 'wiki_detail', lambda client, resource, uuid: PREREQ_DETAIL)
    scdata_sync._sync_wiki_resource(None, 'missions', 'run-1', datetime.utcnow())
    col = get_db()['mission_master']
    doc = col.find_one({'_id': MISSION_ROW['uuid']})
    assert doc['blueprint_uuids'] == [BP_HELMET, BP_RIFLE]
    assert doc['prerequisite_uuids'] == [PRE_A, PRE_B]
    g = doc['prerequisite_groups'][0]
    assert g['required_count'] == 2 and [m['title'] for m in g['missions']] == [
        'Advanced Tracker License Certification', 'Active Bounty Evaluation']

    monkeypatch.setattr(scdata_sync, 'wiki_detail', lambda *a: None)
    scdata_sync._sync_wiki_resource(None, 'missions', 'run-2', datetime.utcnow())
    assert col.find_one({'_id': MISSION_ROW['uuid']})['prerequisite_uuids'] == [PRE_A, PRE_B]


def test_parse_prerequisite_groups():
    from src.scdata import parse_prerequisite_groups
    out = parse_prerequisite_groups([
        {'missions': [{'uuid': 'a', 'title': ' A '}, {'title': 'no uuid'}, 'junk']},
        {'required_count': 0, 'missions': []},
        'junk',
    ])
    assert out == [{'required_count': 1, 'missions': [{'uuid': 'a', 'title': 'A'}],
                    'required_tags': [], 'excluded_tags': []}]


def test_mission_chain_prerequisites_and_unlocks(missions):
    """詳情帶前置任務（中文標題、能不能點開）與反查的「完成後可接」；看不到的任務不能點、也不列。"""
    groups = [{'required_count': 2, 'missions': [{'uuid': 'm1', 'title': 'Alpha Job'},
                                                  {'uuid': 'gone', 'title': 'Gone Job'}]}]
    get_db()['mission_master'].update_one({'_id': 'm2'}, {'$set': {
        'prerequisite_groups': groups, 'prerequisite_uuids': ['m1', 'gone']}})
    _insert_mission('m4', 'Hidden Follow', player_visible=False,
                    prerequisite_groups=[{'required_count': 1, 'missions': [{'uuid': 'm1', 'title': 'Alpha Job'}]}],
                    prerequisite_uuids=['m1'])
    m2 = Mission.get('m2')
    pre = m2['prerequisite_groups'][0]['missions']
    assert [(p['uuid'], p['title_zh'], p['linkable']) for p in pre] == [('m1', '甲任務', True), ('gone', None, False)]
    assert 'prerequisite_uuids' not in m2
    assert [u['uuid'] for u in Mission.get('m1')['unlocks']] == ['m2', 'm4']
    assert [u['uuid'] for u in Mission.get('m1', visible_only=True)['unlocks']] == ['m2']
    row = {r['_id']: r for r in Mission.list_all()[0]}
    assert [u['uuid'] for u in row['m1']['unlocks']] == ['m2', 'm4'] and row['m3']['unlocks'] == []


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


def test_has_reward_filter_and_sort():
    _insert_mission('r1', 'Fixed small', reward_min=1000, reward_max=0)
    _insert_mission('r2', 'Dynamic', reward_min=None, reward_max=None)
    _insert_mission('r3', 'Fixed big', reward_min=5000, reward_max=0)
    rows, total = Mission.list_all(has_reward=True, query='Fixed')
    assert {r['_id'] for r in rows} == {'r1', 'r3'}
    rows, _ = Mission.list_all(has_reward=True, sort_by='reward', sort_dir='desc')
    assert [r['_id'] for r in rows][:2] == ['r3', 'r1']
    rows, _ = Mission.list_all(has_reward=True, query='Dynamic')
    assert rows == []



def test_glued_title_and_translated_fills(seed_translations):
    """Wiki 標題兩段黏在一起（"...LargeMaster Rank - ..."）時分開比對；代入值（等級、規模）也翻成中文，
    沒有值的航線範圍欄位直接拿掉。"""
    seed_translations({
        'Covalex_HaulCargo_MultiToSingle_title': ('~mission(ReputationRank) Rank - ~mission(CargoGradeToken) Cargo Haul',
                                                  '~mission(ReputationRank) 等級 - ~mission(CargoRouteToken) ~mission(CargoGradeToken) 貨物運送'),
        'RepStanding_TransportGuild_Rank6': ('Master', '大師'),
        'HaulCargo_CargoGrade_Bulk': ('Large', '大型'),
    })
    got = Z.mission_text_zh('Master | [CargoRouteToken] LargeMaster Rank - Large Cargo Haul')
    assert got['title_zh'] == '大師 等級 - 大型 貨物運送'
    assert got['title_key'] == 'covalex_haulcargo_multitosingle_title'
    # 一般標題照舊整段比對
    assert Z.mission_text_zh('Master Rank - Large Cargo Haul')['title_zh'] == '大師 等級 - 大型 貨物運送'


def test_list_name_search_rules(missions):
    """任務名稱搜尋：多個關鍵字都要符合、英文比字首、中文任意位置；字首找不到才放寬（meta['match']）。"""
    assert [r['_id'] for r in Mission.list_all(query='job alpha')[0]] == ['m1']
    assert [r['_id'] for r in Mission.list_all(query='甲')[0]] == ['m1']
    meta = {}
    assert [r['_id'] for r in Mission.list_all(query='eta', meta=meta)[0]] == ['m2'] and meta['match'] == 'loose'
    # 沒指定排序時依相符程度：名稱開頭就符合的排前面
    assert [r['_id'] for r in Mission.list_all(query='job')[0]] == ['m1', 'm2', 'm3']


def test_missions_for_commodity(client):
    """礦物頁「用在哪些任務」：hauling_summary 名稱相同（不分大小寫、可帶括號說明）的任務。"""
    col = get_db()['mission_master']
    base = {'is_current': True, 'title': 'Haul', 'star_systems': []}
    col.insert_many([
        {**base, '_id': 'm1', 'title': 'Ore run', 'reward_max': 5000,
         'hauling_summary': [{'name': 'Agricium (Ore)', 'min_amount': 10, 'max_amount': 20}]},
        {**base, '_id': 'm2', 'title': 'Refined', 'reward_max': 9000,
         'hauling_summary': [{'name': 'Waste', 'min_amount': 1}, {'name': 'agricium', 'min_amount': 3, 'max_amount': 3}]},
        {**base, '_id': 'm3', 'hauling_summary': [{'name': 'Agricium Pure', 'min_amount': 1}]},
        {**base, '_id': 'm4', 'is_current': False, 'hauling_summary': [{'name': 'Agricium'}]},
    ])
    rows = client.get('/mission/by-commodity?name=Agricium').get_json()['data']
    assert [r['_id'] for r in rows] == ['m2', 'm1']
    assert rows[0]['haul'] == {'name': 'agricium', 'min_amount': 3, 'max_amount': 3}
    assert 'hauling_summary' not in rows[0]
    assert client.get('/mission/by-commodity').get_json()['data'] == []
