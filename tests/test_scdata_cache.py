"""靜態 JSON 檔的資料庫快取（src/scdata_cache.py）＋ fetch_json_url 的 ETag／304 流程。"""
import io
import json

import httpx
import pytest

from src import scdata, scdata_cache
from src.mongo import get_db

URL = 'https://raw.example/ships.json'


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(scdata.time, 'sleep', lambda s: None)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_store_and_load_list(app):
    rows = scdata_cache.store(URL, io.BytesIO(b' [{"a": 1}, {"a": 2.5, "b.c": "x"}, 3]'), list, etag='e1')
    assert len(rows) == 3
    assert list(rows) == [{'a': 1}, {'a': 2.5, 'b.c': 'x'}, 3]
    again = scdata_cache.load(URL, list)
    assert list(again) == list(rows)
    assert scdata_cache.load(URL, dict) is None          # 種類不對


def test_store_dict_keeps_order(app):
    d = scdata_cache.store(URL, io.BytesIO(b'{"z": 1, "a": {"x": [1, 2]}}'), dict)
    assert d == {'z': 1, 'a': {'x': [1, 2]}} and list(d) == ['z', 'a']
    assert scdata_cache.load(URL, dict) == d


def test_store_rejects_wrong_type_and_broken_json(app):
    with pytest.raises(ValueError, match='預期 JSON list'):
        scdata_cache.store(URL, io.BytesIO(b'{"a": 1}'), list)
    with pytest.raises(ValueError, match='解析失敗'):
        scdata_cache.store(URL, io.BytesIO(b'[{"a": 1}, {"a": '), list)
    # 寫到一半失敗不留殘骸
    assert get_db()[scdata_cache.ROWS].count_documents({}) == 0
    assert scdata_cache.meta(URL) is None


def test_keeps_only_recent_versions(app):
    for i in range(4):
        scdata_cache.store(URL, io.BytesIO(json.dumps([i, i]).encode()), list)
    m = scdata_cache.meta(URL)
    assert len(m['gens']) == scdata_cache.KEEP_GENS
    assert set(get_db()[scdata_cache.ROWS].distinct('gen', {'url': URL})) == set(m['gens'])
    assert list(scdata_cache.load(URL, list)) == [3, 3]


def test_fetch_uses_etag_and_304(app):
    calls = []

    def handler(request):
        calls.append(request.headers.get('If-None-Match'))
        if request.headers.get('If-None-Match') == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, headers={'ETag': '"v1"'}, content=b'[{"id": 1}, {"id": 2}]')

    client = _client(handler)
    first = scdata.fetch_json_url(client, URL, list, label='ships')
    assert [r['id'] for r in first] == [1, 2]
    second = scdata.fetch_json_url(client, URL, list, label='ships')
    assert [r['id'] for r in second] == [1, 2]
    assert calls == [None, '"v1"']                  # 第二次帶 ETag、上游回 304 就不下載
    assert scdata_cache.meta(URL)['checked_at']


def test_fetch_redownloads_when_cache_incomplete(app):
    def handler(request):
        if request.headers.get('If-None-Match'):
            return httpx.Response(304)
        return httpx.Response(200, headers={'ETag': '"v1"'}, content=b'[1, 2, 3]')

    client = _client(handler)
    scdata.fetch_json_url(client, URL, list)
    get_db()[scdata_cache.ROWS].delete_one({'url': URL, 'i': 0})     # 資料庫那份壞掉
    assert list(scdata.fetch_json_url(client, URL, list)) == [1, 2, 3]


def test_fetch_retries_bad_json_then_fails(app):
    client = _client(lambda request: httpx.Response(200, content=b'<html>maintenance</html>'))
    with pytest.raises(scdata.ScDataError, match='重試'):
        scdata.fetch_json_url(client, URL, list)
    assert scdata_cache.meta(URL) is None


def test_fetch_new_version_replaces_old(app):
    state = {'v': 1}

    def handler(request):
        v = state['v']
        if request.headers.get('If-None-Match') == f'"v{v}"':
            return httpx.Response(304)
        return httpx.Response(200, headers={'ETag': f'"v{v}"'}, content=json.dumps([v]).encode())

    client = _client(handler)
    assert list(scdata.fetch_json_url(client, URL, list)) == [1]
    state['v'] = 2
    assert list(scdata.fetch_json_url(client, URL, list)) == [2]


def test_store_splits_into_chunks(app, monkeypatch):
    monkeypatch.setattr(scdata_cache, 'CHUNK_ITEMS', 3)
    rows = scdata_cache.store(URL, io.BytesIO(json.dumps(list(range(10))).encode()), list)
    assert list(rows) == list(range(10)) and len(rows) == 10
    assert get_db()[scdata_cache.ROWS].count_documents({'url': URL}) == 4
    assert scdata_cache.meta(URL)['chunks'] == 4
