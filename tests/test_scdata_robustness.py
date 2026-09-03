"""同步的兩個「安靜地毀掉主檔」路徑的迴歸測試。

### 1. 抓取不完整就下架整份主檔

Wiki API 是跟著 `links.next` 走分頁的。只要某次回應少了 `links.next`
（上游出錯、中間有快取代理、剛好在 deploy），迴圈就提早結束：
`seen=100` 而實際有 20,000 筆，然後把其餘 19,900 筆全部標成
`is_current=False`，這一輪還記成成功。所有主檔查詢都過濾
`is_current=True`，所以症狀是物品搜尋、bot autocomplete、庫存名稱
全部變空 —— 而且要等下一次完整同步才會恢復。
舊版只擋 `seen == 0`，擋不到這種「短少但非零」的情況。

### 2. get_json 的例外路徑

上游回 200 + HTML 維護頁（JSONDecodeError）、回 JSON 陣列、
或 429 帶 HTTP-date 格式的 Retry-After，舊版都不在重試的 except 裡，
會直接把整輪同步炸掉，而且錯誤訊息是 `重試 5 次後仍失敗: None`。
"""
import httpx
import pytest

from src import scdata
from src.scdata import ScDataError, _retry_after_seconds, get_json


# ── get_json 的例外路徑 ───────────────────────────────────────

def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_html_maintenance_page_is_retried_not_crashed(monkeypatch):
    """200 + HTML 是最常見的「上游掛了但沒回錯誤碼」，要走重試而不是爆掉。"""
    monkeypatch.setattr(scdata.time, 'sleep', lambda *_: None)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, text='<html>maintenance</html>')

    with _client(handler) as client:
        with pytest.raises(ScDataError) as exc:
            get_json(client, 'https://example.test/items')

    assert len(calls) == scdata.SCDATA_MAX_RETRIES     # 真的重試過
    assert 'None' not in str(exc.value)                # 訊息要講得出原因


def test_json_array_payload_is_treated_as_bad_format(monkeypatch):
    """呼叫端會做 payload.get('data')，回陣列的話那裡會 AttributeError ——
    在這層就擋掉，錯誤訊息才指得到正確的地方。"""
    monkeypatch.setattr(scdata.time, 'sleep', lambda *_: None)

    with _client(lambda request: httpx.Response(200, json=[1, 2, 3])) as client:
        with pytest.raises(ScDataError):
            get_json(client, 'https://example.test/items')


def test_valid_json_object_is_returned(monkeypatch):
    with _client(lambda request: httpx.Response(200, json={'data': [{'x': 1}]})) as client:
        assert get_json(client, 'https://example.test/items') == {'data': [{'x': 1}]}


def test_server_error_then_success(monkeypatch):
    monkeypatch.setattr(scdata.time, 'sleep', lambda *_: None)
    state = {'n': 0}

    def handler(request):
        state['n'] += 1
        if state['n'] == 1:
            return httpx.Response(503, text='upstream down')
        return httpx.Response(200, json={'data': []})

    with _client(handler) as client:
        assert get_json(client, 'https://example.test/items') == {'data': []}
    assert state['n'] == 2


def test_error_message_names_the_failure_even_for_5xx_only(monkeypatch):
    """全部都是 5xx 時，舊版 last_err 從沒被賦值 → 訊息是「仍失敗: None」。"""
    monkeypatch.setattr(scdata.time, 'sleep', lambda *_: None)

    with _client(lambda request: httpx.Response(502, text='bad gateway')) as client:
        with pytest.raises(ScDataError) as exc:
            get_json(client, 'https://example.test/items')
    assert '502' in str(exc.value)


# ── Retry-After 解析 ─────────────────────────────────────────

def test_retry_after_accepts_seconds():
    assert _retry_after_seconds('12', fallback=1.0) == 12.0


def test_retry_after_accepts_http_date():
    """RFC 9110 允許 HTTP-date，舊版 float() 會 ValueError 且沒被攔。"""
    from email.utils import format_datetime
    from datetime import datetime, timedelta, timezone

    when = datetime.now(timezone.utc) + timedelta(seconds=30)
    got = _retry_after_seconds(format_datetime(when), fallback=1.0)
    assert 20 <= got <= 40


def test_retry_after_falls_back_on_garbage():
    assert _retry_after_seconds('nonsense', fallback=2.5) == 2.5
    assert _retry_after_seconds('', fallback=2.5) == 2.5


def test_retry_after_never_negative():
    """已經過去的時間點不該變成負數 sleep。"""
    assert _retry_after_seconds('Wed, 21 Oct 2015 07:28:00 GMT', fallback=1.0) == 0.0


def test_429_with_http_date_is_retried(monkeypatch):
    monkeypatch.setattr(scdata.time, 'sleep', lambda *_: None)
    state = {'n': 0}

    def handler(request):
        state['n'] += 1
        if state['n'] == 1:
            return httpx.Response(429, headers={'Retry-After': 'Wed, 21 Oct 2015 07:28:00 GMT'})
        return httpx.Response(200, json={'data': []})

    with _client(handler) as client:
        assert get_json(client, 'https://example.test/items') == {'data': []}


# ── 下架護欄 ─────────────────────────────────────────────────

def test_incomplete_fetch_does_not_retire_the_catalogue(monkeypatch):
    """主檔有 1000 筆上架，這次只抓到 100 筆 → 應該拋錯，主檔維持原狀。"""
    from tasks import scdata_sync
    from src.mongo import get_db

    db = get_db()
    db['item_master'].insert_many([
        {'_id': f'uuid-{i}', 'name': f'Item {i}', 'is_current': True}
        for i in range(1000)
    ])

    monkeypatch.setattr(scdata_sync, 'wiki_rows',
                        lambda client, resource: iter([
                            {'uuid': f'uuid-{i}', 'name': f'Item {i}'} for i in range(100)
                        ]))

    with pytest.raises(Exception) as exc:
        scdata_sync._sync_wiki_resource(None, 'items', 'run-1', __import__('datetime').datetime.utcnow())

    assert '不完整' in str(exc.value) or '80%' in str(exc.value)
    # 關鍵：沒有任何一筆被下架
    assert db['item_master'].count_documents({'is_current': {'$ne': False}}) == 1000


def test_first_sync_with_empty_collection_is_allowed(monkeypatch):
    """首次同步沒有基準筆數，只要有資料就要放行（否則永遠灌不進去）。"""
    from tasks import scdata_sync
    from src.mongo import get_db

    monkeypatch.setattr(scdata_sync, 'wiki_rows',
                        lambda client, resource: iter([
                            {'uuid': 'uuid-1', 'name': 'MedPen'},
                        ]))

    result = scdata_sync._sync_wiki_resource(
        None, 'items', 'run-1', __import__('datetime').datetime.utcnow())
    assert result['seen'] == 1
    assert get_db()['item_master'].count_documents({'is_current': {'$ne': False}}) == 1


def test_zero_rows_still_blocked(monkeypatch):
    """原本就有的護欄不能退化。"""
    from tasks import scdata_sync

    monkeypatch.setattr(scdata_sync, 'wiki_rows', lambda client, resource: iter([]))
    with pytest.raises(Exception):
        scdata_sync._sync_wiki_resource(
            None, 'items', 'run-1', __import__('datetime').datetime.utcnow())
