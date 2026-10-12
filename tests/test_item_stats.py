"""成品基礎數值（src/models/item_stats.py）：品質試算把倍率換算成實際數值用。"""
from src.models.item_stats import base_stats, for_blueprint, norm
from src.mongo import get_db

RAW = {
    'description_data': [
        {'name': 'Carrying Capacity', 'value': '8.0 µSCU'},
        {'name': 'Damage Reduction', 'value': '40%'},
        {'name': 'Item Type', 'value': 'Heavy Armor'},
        {'name': 'Radiation Protection', 'value': '26800 REM'},
        {'name': 'Temp. Rating', 'value': '-70 / 100 °C'},
    ],
    'clothing': {'temp_resistance_min': -70, 'temp_resistance_max': 100,
                 'damage_resistance_map': {'physical': 0.6},
                 'radiation_resistance': {'maximum_radiation_capacity': 26800, 'radiation_dissipation_rate': 145.8}},
}


def test_base_stats_armor():
    s = base_stats(RAW)
    assert s[norm('Damage Mitigation')]['value'] == 40 and s[norm('Damage Mitigation')]['unit'] == '%'
    assert s[norm('Min Temp')] == {'name': 'Min Temp', 'value': -70, 'unit': '°C'}
    assert s[norm('Max Temp')]['value'] == 100
    assert s[norm('Radiation Scrub Rate')]['value'] == 145.8
    assert s[norm('Carrying Capacity')]['unit'] == 'µSCU'
    assert norm('Item Type') not in s, '不是數字的不列'
    assert norm('Temp. Rating') not in s, '範圍值不當成單一數字'


def test_damage_reduction_fallback():
    s = base_stats({'clothing': {'damage_resistance_map': {'physical': 0.75}}})
    assert s[norm('Damage Mitigation')]['value'] == 25


def test_for_blueprint(app):
    db = get_db()
    db['blueprint_master'].insert_one({'_id': 'bp1', 'output_item_uuid': 'it1'})
    db['item_master'].insert_one({'_id': 'it1', 'raw': RAW})
    assert for_blueprint('bp1')[norm('Max Temp')]['value'] == 100
    assert for_blueprint('nope') == {}
