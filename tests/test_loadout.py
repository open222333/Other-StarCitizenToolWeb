"""配裝模擬：scunpacked mapper（src/scdata_loadout.py）、資料模型（src/models/loadout.py）、API（/item/loadout）。"""

from src.mongo import get_db
from src.models import loadout
from src.scdata_loadout import compat_types, map_ship_item, map_ship_loadout, ship_tags

GUN = {
    'className': 'GATS_BallisticGatling_S3', 'reference': 'gun-1', 'type': 'WeaponGun', 'subType': 'Gun',
    'size': 3, 'name': 'Mantis GT-220 Gatling',
    'stdItem': {
        'UUID': 'gun-1', 'Grade': 1, 'Mass': 150, 'Tags': ['GATS'],
        'Manufacturer': {'Code': 'GATS', 'Name': 'Gallenson Tactical Systems'},
        'Durability': {'Health': 1500},
        'Ports': [{'PortName': 'BAR1', 'Types': ['WeaponAttachment.Barrel'], 'Uneditable': True}],
        'Ammunition': {'Speed': 1332, 'Range': 2398, 'Capacity': 4314,
                       'Penetration': {'BasePenetrationDistance': 1.7, 'NearRadius': 0.09, 'FarRadius': 0.09}},
        'Weapon': {'RateOfFire': 1600, 'EffectiveRange': 2398, 'Capacity': 4314,
                   'Modes': [{'Name': 'Rapid', 'LocalisedName': '[AUTO]', 'RoundsPerMinute': 1600}],
                   'Damage': {'Sustained': 500, 'AlphaTotal': 32, 'DpsTotal': 853.3,
                              'Alpha': {'Physical': 32, 'Energy': 0}}},
        'ResourceNetwork': {'Usage': {'Power': {'Minimum': 0.1, 'Maximum': 0.1}}},
        'Emission': {'Em': {'Maximum': 36}, 'Ir': 0},
    },
}
SHIELD = {
    'className': 'SHLD_GODI_S03_SureStop_SCItem', 'reference': 'shd-1', 'type': 'Shield', 'subType': 'UNDEFINED',
    'size': 3, 'name': 'SureStop',
    'stdItem': {'UUID': 'shd-1', 'Grade': 2, 'DescriptionData': {'Class': 'Military'},
                'ResourceNetwork': {
                    'States': [{'PowerRanges': [{'Start': 1, 'Modifier': 0.7}, {'Start': 3, 'Modifier': 0.85},
                                                {'Start': 5, 'Modifier': 1}]}],
                    'Usage': {'Power': {'Minimum': 2, 'Maximum': 5}, 'Coolant': {'Minimum': 1.4, 'Maximum': 5}}},
                'Emission': {'Em': {'Maximum': 2060, 'Minimum': 577}, 'Ir': 0},
                'Shield': {'MaxShieldHealth': 105600, 'MaxShieldRegen': 20064,
                           'Absorption': {'Physical': {'Minimum': 0, 'Maximum': 0.45}}}},
}
GIMBAL = {
    'className': 'Mount_Gimbal_S3', 'reference': 'gim-1', 'type': 'Turret', 'subType': 'GunTurret',
    'size': 3, 'name': 'VariPuck S3 Gimbal Mount',
    'stdItem': {'UUID': 'gim-1', 'Ports': [{
        'PortName': 'hardpoint_class_2', 'MinSize': 3, 'MaxSize': 3, 'Uneditable': False,
        'CompatibleTypes': [{'Type': 'WeaponGun', 'SubTypes': ['Gun']}], 'EquippedItem': 'gun-1'}]},
}
PLACEHOLDER = {'className': 'SHLD_S01_Template', 'reference': 'x', 'type': 'Shield', 'size': 1,
               'stdItem': {'UUID': 'x', 'Name': '<= PLACEHOLDER =>'}}
DOOR = {'className': 'Door_X', 'reference': 'd', 'type': 'Door', 'name': 'Door', 'stdItem': {'UUID': 'd'}}

SHIP = {
    'UUID': 'ship-1', 'ClassName': 'ANVL_Arrow', 'Name': 'Anvil Arrow', 'Size': 1, 'Career': 'Combat',
    'Role': 'Light Fighter', 'Crew': 1, 'IsSpaceship': True, 'PortTags': ['anvl_arrow_base'],
    'Health': 9000, 'ShieldHp': 105600, 'PenetrationMultiplier': {'Fuse': 0.7, 'Components': 0.8},
    'Armor': {'Health': 4000, 'DamageMultipliers': {'Physical': 0.7, 'Energy': 0.5},
              'Deflection': {'Physical': 30, 'Energy': 20}},
    'QuantumTravel': {'FuelCapacity': 583, 'Range': 1e11},
    'PowerPools': {'WeaponGun': {'Size': 4}, 'Shield': {'Size': 2}},
    'Power': {'GenerationSegments': 16, 'UsedSegmentsShields': 24,
              'UsedSegmentsGrouped': {'Shield': 5, 'WeaponGun': 0.1, 'FlightController': 4, 'LifeSupportGenerator': 1},
              'MaxSegments': {'Shield': 5, 'WeaponGun': 0, 'FlightController': 4, 'LifeSupportGenerator': 1}},
    'Emission': {'EmShields': 20000, 'IrShields': 7000, 'EmGroupsShields': {'Shield': 2060, 'PowerPlant': 9000,
                                                                            'LifeSupportGenerator': 354}},
    'Cooling': {'GenerationSegments': 68, 'UsedSegmentsShieldsGrouped': {'Shield': 5, 'LifeSupportGenerator': 1,
                                                                        'PowerPlant': 24}},
    'Loadout': [
        {'HardpointName': 'hardpoint_weapon_left', 'ClassName': 'Mount_Gimbal_S3', 'UUID': 'gim-1',
         'Editable': True, 'MinSize': 3, 'MaxSize': 3,
         'CompatibleTypes': [{'Type': 'Turret', 'SubTypes': ['GunTurret']}, {'Type': 'WeaponGun', 'SubTypes': ['Gun']}],
         'Loadout': [{'HardpointName': 'hardpoint_class_2', 'ClassName': 'GATS_BallisticGatling_S3', 'UUID': 'gun-1',
                      'Editable': True, 'MinSize': 3, 'MaxSize': 3,
                      'CompatibleTypes': [{'Type': 'WeaponGun', 'SubTypes': ['Gun']}],
                      'Loadout': [{'HardpointName': 'BAR1', 'CompatibleTypes': [{'Type': 'WeaponAttachment'}]}]}]},
        {'HardpointName': 'hardpoint_shield', 'ClassName': 'SHLD_GODI_S03_SureStop_SCItem', 'UUID': 'shd-1',
         'Editable': True, 'MinSize': 1, 'MaxSize': 1, 'CompatibleTypes': [{'Type': 'Shield'}]},
        {'HardpointName': 'hardpoint_pdc', 'ClassName': 'Turret_PDC', 'UUID': 'pdc-1', 'PortTags': ['PDC'],
         'RequiredTags': ['PDC'], 'Editable': True, 'MinSize': 2, 'MaxSize': 2, 'CompatibleTypes': [{'Type': 'Turret'}]},
        {'HardpointName': 'hardpoint_turret_camera', 'ClassName': 'Camera_Turret', 'Type': 'Turret.GunTurret',
         'RequiredTags': ['ANVL_Arrow_Blade'], 'Editable': False, 'CompatibleTypes': [{'Type': 'Turret'}]},
        {'HardpointName': 'hardpoint_door', 'ClassName': 'Door_X', 'CompatibleTypes': [{'Type': 'Door'}]},
    ],
}


def test_compat_types_expands_sub_types():
    assert compat_types({'CompatibleTypes': [{'Type': 'Radar', 'SubTypes': ['ShortRangeRadar', 'MidRangeRadar']},
                                             {'Type': 'Shield'}]}) == \
        ['Radar.ShortRangeRadar', 'Radar.MidRangeRadar', 'Shield']
    assert compat_types({'Types': ['Missile.Torpedo']}) == ['Missile.Torpedo']


def test_map_ship_item_weapon_stats_and_penetration():
    doc = map_ship_item(GUN)
    assert doc['_id'] == 'gun-1' and doc['type'] == 'WeaponGun' and doc['size'] == 3 and doc['grade'] == 'A'
    s = doc['stats']
    assert (s['alpha'], s['dps'], s['sustained'], s['rpm']) == (32, 853.3, 500, 1600)
    assert s['damage'] == {'physical': 32}
    assert s['pen_distance'] == 1.7 and s['range'] == 2398 and s['ammo'] == 4314
    assert s['power_use'] == [0.1, 0.1] and s['em'] == 36
    assert doc['ports'] == []          # 武器配件槽不列


def test_map_ship_item_shield_and_ports():
    shield = map_ship_item(SHIELD)
    assert shield['stats']['hp'] == 105600 and shield['stats']['regen'] == 20064
    assert shield['stats']['absorption'] == {'physical': [0, 0.45]}
    assert shield['item_class'] == 'Military' and shield['grade'] == 'B'
    gimbal = map_ship_item(GIMBAL)
    assert gimbal['ports'] == [{'port': 'hardpoint_class_2', 'types': ['WeaponGun.Gun'], 'min': 3, 'max': 3,
                                'editable': True, 'default': 'gun-1'}]


def test_map_ship_item_power_ranges():
    s = map_ship_item(SHIELD)['stats']
    assert s['power_ranges'] == [[1, 0.7], [3, 0.85], [5, 1]]
    assert s['power_use'] == [2, 5] and s['coolant_use'] == [1.4, 5] and s['em'] == 2060
    # 倍率都是 1 的不存
    assert 'power_ranges' not in map_ship_item(GUN)['stats']


def test_map_ship_loadout_power():
    pw = map_ship_loadout(SHIP)['power']
    assert pw['gen'] == 16 and pw['weapon_pool'] == 4
    assert pw['groups']['FlightController'] == {'power': 4, 'em': 0, 'coolant': 0}
    assert pw['groups']['LifeSupportGenerator'] == {'power': 1, 'em': 354, 'coolant': 1}
    assert 'PowerPlant' not in pw['groups']
    assert pw['baseline']['em'] == 20000 and pw['baseline']['coolant_gen'] == 68
    assert pw['signal'] == {'em': 1, 'ir': 1, 'cs': 1}
    assert map_ship_loadout({**SHIP, 'Power': {}})['power'] is None


def test_map_ship_item_skips_placeholder_and_unrelated():
    assert map_ship_item(PLACEHOLDER) is None
    assert map_ship_item(DOOR) is None


def test_map_ship_loadout_prunes_tree():
    doc = map_ship_loadout(SHIP)
    ids = [s['id'] for s in doc['slots']]
    # 門不列、只有攝影機的鎖死砲塔不列
    assert ids == ['hardpoint_weapon_left', 'hardpoint_shield', 'hardpoint_pdc']
    weapon = doc['slots'][0]
    assert weapon['item'] == 'gim-1' and weapon['types'] == ['Turret.GunTurret', 'WeaponGun.Gun']
    assert [c['id'] for c in weapon['children']] == ['hardpoint_weapon_left/hardpoint_class_2']
    assert weapon['children'][0]['children'] == []           # 武器配件槽不列
    assert doc['slots'][2]['tags'] == ['PDC']
    assert doc['hull']['armor_damage'] == {'physical': 0.7, 'energy': 0.5}
    assert doc['hull']['deflection'] == {'physical': 30, 'energy': 20}
    assert doc['hull']['pen_multiplier'] == {'fuse': 0.7, 'components': 0.8}
    assert doc['fuel']['quantum'] == 583


def test_ship_tags_skip_port_scoped():
    # PDC 只在那一格（PortTags）才有，不算船本身的標籤
    assert ship_tags(SHIP) == ['anvl_arrow_base', 'anvl_arrow_blade']


def _seed():
    db = get_db()
    for row in (GUN, SHIELD, GIMBAL):
        db['ship_item_master'].insert_one({**map_ship_item(row), 'is_current': True})
    ship = map_ship_loadout(SHIP)
    db['ship_loadout_master'].insert_one({**ship, 'is_current': True})
    # NPC 變體：同名只留一筆
    db['ship_loadout_master'].insert_one({**ship, '_id': 'ship-ai', 'class_name': 'ANVL_Arrow_PU_AI', 'is_current': True})


def test_ships_dedupes_variants(app):
    _seed()
    rows = loadout.ships()
    assert [r['id'] for r in rows] == ['ship-1']
    assert rows[0]['name'] == 'Anvil Arrow' and rows[0]['role'] == 'Light Fighter'


def test_ship_includes_items_and_port_defaults(app):
    _seed()
    doc = loadout.ship('ship-1')
    assert doc['id'] == 'ship-1'
    assert set(doc['items']) == {'gim-1', 'gun-1', 'shd-1'}
    assert loadout.ship('nope') is None
    # 只給雲台也會帶出它預設裝的武器
    assert set(loadout.items_by_ids(['gim-1'])) == {'gim-1', 'gun-1'}


def test_items_by_type(app):
    _seed()
    assert [d['id'] for d in loadout.items(types=['WeaponGun'])] == ['gun-1']
    assert {d['id'] for d in loadout.items(types=['Shield'], ids=['gim-1'])} == {'shd-1', 'gim-1', 'gun-1'}
    assert loadout.items(types=['$where']) == []


def test_loadout_api(client, auth_headers):
    _seed()
    r = client.get('/item/loadout/ships', headers=auth_headers)
    assert r.status_code == 200 and r.get_json()['data'][0]['id'] == 'ship-1'
    r = client.get('/item/loadout/ships/ship-1', headers=auth_headers)
    assert r.status_code == 200 and r.get_json()['data']['slots'][0]['id'] == 'hardpoint_weapon_left'
    assert client.get('/item/loadout/ships/nope', headers=auth_headers).status_code == 404
    r = client.get('/item/loadout/items?types=Shield', headers=auth_headers)
    assert [d['id'] for d in r.get_json()['data']] == ['shd-1']
    assert client.get('/item/loadout/items', headers=auth_headers).status_code == 400
    assert client.get('/item/loadout/ships').status_code == 200  # 不登入也能用（@public_api）
