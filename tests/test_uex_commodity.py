"""UEX 商品縮寫與礦物的關聯（src/models/uex_commodity.py、app/mining/view.py）。"""
from src.models.mining import MiningDeposit
from src.models.uex_commodity import UexCommodity, base_name
from src.mongo import get_db


def _uex(db, _id, code, name, is_raw=0):
    db['uex_commodities'].insert_one({'_id': str(_id), 'id': _id, 'code': code, 'name': name,
                                      'kind': 'Metal', 'is_raw': is_raw})


def _deposit(db, parts):
    db['mining_deposit_master'].insert_one({
        '_id': 'd1', 'key': 'd1', 'deposit_name': 'Rock', 'deposit_name_lower': 'rock',
        'tier': 'common', 'is_current': True,
        'parts': [{'resource_key': k, 'resource_name': n} for k, n in parts],
    })


def _seed(db):
    _uex(db, 1, 'QUAN', 'Quantainium')
    _uex(db, 2, 'QUAR', 'Quantainium (Raw)', is_raw=1)
    _uex(db, 3, 'CARI', 'Carinite')
    _uex(db, 4, 'CARP', 'Carinite (Pure)')
    _uex(db, 5, 'STIL', 'Stileron')
    _deposit(db, [('Ore_Quan', 'Quantainium (Ore)'), ('Ore_CariPure', 'Carinite (Pure)'),
                  ('Ore_Stil', 'Raw Stileron'), ('Ore_Odd', 'Oddium')])


def test_base_name():
    assert base_name(' Stileron (Ore) ') == 'stileron'
    assert base_name('Raw Ouratite') == 'ouratite'
    assert base_name('Carinite (Pure)') == 'carinite'


def test_links_auto_match(app):
    db = get_db()
    _seed(db)
    parts = {p['resource_key']: p['uex'] for p in MiningDeposit.list_all()[0]['parts']}
    assert parts['Ore_Quan']['code'] == 'QUAN' and parts['Ore_Quan']['raw_code'] == 'QUAR', '主要取非原礦'
    assert parts['Ore_CariPure']['code'] == 'CARP', '完全同名優先，不會被去後綴的 Carinite 搶走'
    assert parts['Ore_Stil']['code'] == 'STIL'
    assert parts['Ore_Odd']['code'] is None and parts['Ore_Odd']['source'] == 'auto'


def test_manual_link_api(client, auth_headers):
    db = get_db()
    _seed(db)
    url = '/mining/minerals/Ore_Odd/uex'
    assert client.put(url, json={'uex_id': '5'}, headers=auth_headers).status_code == 200
    links = UexCommodity.links_for({'Ore_Odd': 'Oddium', 'Ore_Quan': 'Quantainium (Ore)'})
    assert links['Ore_Odd']['code'] == 'STIL' and links['Ore_Odd']['source'] == 'manual'

    # 指定成不關聯
    client.put('/mining/minerals/Ore_Quan/uex', json={'uex_id': ''}, headers=auth_headers)
    assert UexCommodity.links_for({'Ore_Quan': 'Quantainium (Ore)'})['Ore_Quan'] == \
        {'code': None, 'raw_code': None, 'raw_id': None, 'source': 'manual'}
    # 清掉手動設定 → 回到自動比對
    client.put('/mining/minerals/Ore_Quan/uex', json={'uex_id': None}, headers=auth_headers)
    assert UexCommodity.links_for({'Ore_Quan': 'Quantainium (Ore)'})['Ore_Quan']['code'] == 'QUAN'

    assert client.put(url, json={'uex_id': '999'}, headers=auth_headers).status_code == 400
    assert client.put(url, json={}, headers=auth_headers).status_code == 400

    body = client.get('/mining/uex-commodities', headers=auth_headers).get_json()
    assert [r['code'] for r in body['data']] == ['CARI', 'CARP', 'QUAN', 'QUAR', 'STIL']


def test_commodity_detail_list(client, auth_headers):
    db = get_db()
    _seed(db)
    body = client.get('/mining/uex-commodities/detail', headers=auth_headers).get_json()
    rows = {r['code']: r for r in body['data']}
    assert [m['resource_key'] for m in rows['QUAN']['minerals']] == ['Ore_Quan']
    assert rows['QUAR']['minerals'][0]['as_raw'] is True, '原礦那筆也看得到關聯的礦物'
    assert rows['CARI']['minerals'] == []
    assert rows['QUAN']['is_raw'] == 0 and rows['QUAN']['price_buy'] is None
