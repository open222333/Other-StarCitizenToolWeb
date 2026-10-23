"""後台「資料庫檢視」（src/models/data_browser.py、/data/collections）。"""
from datetime import datetime

from bson import ObjectId

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
