"""後台「資料庫檢視」（src/models/data_browser.py、/data/collections）。"""
from datetime import datetime

from bson import ObjectId
import pytest

from src.models import data_browser
from src.mongo import get_db


def _seed():
    db = get_db()
    db['uex_refinery_yields'].insert_many([
        {'_id': '1:10', 'commodity_name': 'Gold', 'terminal_name': 'ARC-L1', 'value': 3,
         'raw': {'big': 'x' * 500}, 'tags': ['a'] * 100},
        {'_id': '2:10', 'commodity_name': 'Quantanium', 'terminal_name': 'CRU-L1', 'value': -2, 'extra': True},
    ])
    db['sync_runs'].insert_one({'_id': ObjectId(), 'started_at': datetime(2026, 1, 2, 3, 4)})


def test_catalog_lists_only_whitelisted(app):
    _seed()
    names = {c['name']: c for cat in data_browser.catalog() for c in cat['collections']}
    assert names['uex_refinery_yields']['count'] == 2
    assert 'users' not in names and 'players' not in names


def test_list_columns_preview_and_search(app):
    _seed()
    data = data_browser.list_docs('uex_refinery_yields')
    assert data['columns'] == ['_id', 'commodity_name', 'terminal_name', 'value', 'tags', 'extra']
    row = data['rows'][0]
    assert 'raw' not in row and isinstance(row['tags'], str) and row['tags'].endswith('…')
    assert [r['_id'] for r in data_browser.list_docs('uex_refinery_yields', q='quant')['rows']] == ['2:10']
    assert [r['_id'] for r in data_browser.list_docs('uex_refinery_yields', field='value', q='-2')['rows']] == ['2:10']
    assert [r['_id'] for r in data_browser.list_docs('uex_refinery_yields', sort_by='value', sort_dir='desc')['rows']] == ['1:10', '2:10']


def test_large_collection_searches_name_like_fields_only(app, monkeypatch):
    _seed()
    monkeypatch.setattr(data_browser, 'LARGE_COLLECTION', 1)
    # terminal_name 是名稱類欄位，照樣搜得到；value 不是，全部欄位搜尋時不比對
    assert [r['_id'] for r in data_browser.list_docs('uex_refinery_yields', q='CRU')['rows']] == ['2:10']
    assert data_browser.list_docs('uex_refinery_yields', q='-2')['rows'] == []
    assert [r['_id'] for r in data_browser.list_docs('uex_refinery_yields', field='value', q='-2')['rows']] == ['2:10']


def test_translations_search_nested_text(app):
    get_db()['sc_translations'].insert_many([
        {'_id': 'vehicle_NameX', 'key_lower': 'vehicle_namex', 'en_lower': 'x ship', 'text': {'en': 'X Ship', 'zh-TW': '某艘船'}},
        {'_id': 'k' * 300, 'key_lower': 'long', 'text': {'en': 'Long'}},
    ])
    data = data_browser.list_docs('sc_translations', q='某艘')
    assert [r['_id'] for r in data['rows']] == ['vehicle_NameX'] and 'text.zh-TW' in data['search_fields']
    assert [r['_id'] for r in data_browser.list_docs('sc_translations', field='text.en', q='x ship')['rows']] == ['vehicle_NameX']
    assert data_browser.list_docs('sc_translations', q='long')['rows'][0]['_id'] == 'k' * 300, '_id 不截斷'


def test_doc_returns_full_document(app):
    _seed()
    assert data_browser.doc('uex_refinery_yields', '1:10')['raw']['big'] == 'x' * 500
    sid = str(get_db()['sync_runs'].find_one()['_id'])
    assert data_browser.doc('sync_runs', sid)['started_at'].startswith('2026-01-02')


def test_api(client, auth_headers, app):
    _seed()
    body = client.get('/data/collections', headers=auth_headers).get_json()
    assert body['success'] and body['data'][0]['category']
    res = client.get('/data/collections/uex_refinery_yields?field=commodity_name&q=gold', headers=auth_headers)
    assert res.get_json()['data']['total'] == 1
    assert client.get('/data/collections/users', headers=auth_headers).status_code == 404
    assert client.get('/data/collections/uex_refinery_yields?field=nope&q=x', headers=auth_headers).status_code == 400
    assert client.get('/data/collections/uex_refinery_yields/doc?id=1:10', headers=auth_headers).get_json()['data']['value'] == 3
    assert client.get('/data/collections').status_code == 401


def test_all_fields_flattened_and_filters(app):
    db = get_db()
    db['starmap_master'].insert_many([
        {'_id': 'a', 'name': 'Port A', 'pos': {'x': 1, 'y': 2}, 'uex_is_auto_load': True, 'uex_max_container_size': 32,
         'raw': {'class': 'Big'}},
        {'_id': 'b', 'name': 'Port B', 'pos': {'x': 5, 'y': 6}, 'uex_is_auto_load': False, 'tags': []},
        {'_id': 'c', 'name': 'Moon C'},
    ])
    data = data_browser.list_docs('starmap_master')
    assert {'pos.x', 'pos.y', 'uex_max_container_size'} <= set(data['columns']) and 'raw' not in data['columns']
    assert data['rows'][0]['pos.x'] == 1

    def ids(*filters):
        return [r['_id'] for r in data_browser.list_docs('starmap_master', filters=list(filters))['rows']]
    assert ids({'field': 'name', 'op': 'contains', 'value': 'port'}) == ['a', 'b']
    assert ids({'field': 'name', 'op': 'not_contains', 'value': 'port'}) == ['c']
    assert ids({'field': 'uex_is_auto_load', 'op': 'eq', 'value': 'true'}) == ['a']
    assert ids({'field': 'pos.x', 'op': 'gte', 'value': '2'}) == ['b']
    assert ids({'field': 'uex_max_container_size', 'op': 'empty'}) == ['b', 'c']
    assert ids({'field': 'pos', 'op': 'not_empty'}, {'field': 'pos.y', 'op': 'lt', 'value': '6'}) == ['a']
    assert ids({'field': 'raw.class', 'op': 'eq', 'value': 'Big'}) == ['a'], 'raw 裡的欄位也能篩'
    with pytest.raises(ValueError):
        ids({'field': 'pos.x', 'op': 'gt', 'value': 'abc'})
    with pytest.raises(ValueError):
        ids({'field': '$where', 'op': 'eq', 'value': '1'})


def test_api_filters(client, auth_headers, app):
    get_db()['uex_terminals'].insert_many([{'_id': '1', 'id': 1, 'name': 'A', 'is_auto_load': 1},
                                           {'_id': '2', 'id': 2, 'name': 'B', 'is_auto_load': 0}])
    import json as _json
    f = _json.dumps([{'field': 'is_auto_load', 'op': 'eq', 'value': '1'}])
    res = client.get(f'/data/collections/uex_terminals?filters={f}', headers=auth_headers).get_json()
    assert [r['_id'] for r in res['data']['rows']] == ['1']
    assert client.get('/data/collections/uex_terminals?filters=[bad', headers=auth_headers).status_code == 400
