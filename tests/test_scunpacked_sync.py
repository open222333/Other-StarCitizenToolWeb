"""scunpacked-data 同步（_sync_scunpacked_resource，tasks/scdata_sync.py）的測試。

跟 _sync_wiki_resource 的保護邏輯是同一套（is_current / retired_at / 80% 下架
門檻），這裡只驗證接到「非分頁、單一 JSON 檔」的來源時邏輯照樣成立——
理由同樣是：上游檔案任何一次抓取異常變短，都不該把既有參考表整批下架。
"""
from datetime import datetime

import pytest

from src.mongo import get_db


@pytest.fixture
def sync_mod():
    import tasks.scdata_sync as m
    return m


def _simple_mapper(row):
    if not row.get('_id'):
        return None
    return {'_id': row['_id'], 'name': row['name']}


def test_scunpacked_sync_writes_current_docs(app, sync_mod, monkeypatch):
    monkeypatch.setattr(sync_mod, 'SCUNPACKED_RESOURCES', {
        'mining_deposits': ('mining_deposit_master', 'resources/resources.json', _simple_mapper),
    })
    monkeypatch.setattr(sync_mod, 'fetch_scunpacked_rows', lambda client, path: [
        {'_id': 'd1', 'name': 'Granite Deposit'},
        {'_id': 'd2', 'name': 'Obsidian Deposit'},
    ])

    result = sync_mod._sync_scunpacked_resource(None, 'mining_deposits', 'run-1', datetime.utcnow())

    assert result == {'resource': 'scunpacked:mining_deposits', 'collection': 'mining_deposit_master',
                      'seen': 2, 'written': 2, 'skipped': 0, 'retired': 0}
    docs = list(get_db()['mining_deposit_master'].find({}, {'_id': 1, 'is_current': 1}))
    assert {d['_id'] for d in docs} == {'d1', 'd2'}
    assert all(d['is_current'] for d in docs)


def test_scunpacked_sync_guards_against_incomplete_fetch(app, sync_mod, monkeypatch):
    monkeypatch.setattr(sync_mod, 'SCUNPACKED_RESOURCES', {
        'mining_deposits': ('mining_deposit_master', 'resources/resources.json', _simple_mapper),
    })
    rows = [{'_id': f'd{i}', 'name': f'Deposit {i}'} for i in range(10)]
    monkeypatch.setattr(sync_mod, 'fetch_scunpacked_rows', lambda client, path: rows)
    sync_mod._sync_scunpacked_resource(None, 'mining_deposits', 'run-1', datetime.utcnow())

    # 第二輪只回 1/10（10% < 80% 門檻），不該直接下架其餘 9 筆 —— 而是判定
    # 抓取不完整，往上拋錯，讓呼叫端走 backoff 重試、既有資料維持原狀。
    monkeypatch.setattr(sync_mod, 'fetch_scunpacked_rows', lambda client, path: rows[:1])
    from src.scdata import ScDataError
    with pytest.raises(ScDataError, match='80%'):
        sync_mod._sync_scunpacked_resource(None, 'mining_deposits', 'run-2', datetime.utcnow())

    d9 = get_db()['mining_deposit_master'].find_one({'_id': 'd9'})
    assert d9['is_current'] is True, '抓取不完整（低於 80% 門檻）不該下架既有資料'


def test_scunpacked_sync_retires_after_full_overlap_drop(app, sync_mod, monkeypatch):
    """跟上一個測試的差別：這裡模擬「上游真的把某礦床下架了」（沒有低於 80%
    門檻），此時該正常標成 is_current=False，而不是永遠卡在 True。"""
    monkeypatch.setattr(sync_mod, 'SCUNPACKED_RESOURCES', {
        'mining_deposits': ('mining_deposit_master', 'resources/resources.json', _simple_mapper),
    })
    rows = [{'_id': f'd{i}', 'name': f'Deposit {i}'} for i in range(10)]
    monkeypatch.setattr(sync_mod, 'fetch_scunpacked_rows', lambda client, path: rows)
    sync_mod._sync_scunpacked_resource(None, 'mining_deposits', 'run-1', datetime.utcnow())

    # 第二輪掉了 1 筆（9/10 = 90% >= 80% 門檻），應該正常下架那 1 筆
    monkeypatch.setattr(sync_mod, 'fetch_scunpacked_rows', lambda client, path: rows[:9])
    result = sync_mod._sync_scunpacked_resource(None, 'mining_deposits', 'run-2', datetime.utcnow())

    assert result['retired'] == 1
    retired_doc = get_db()['mining_deposit_master'].find_one({'_id': 'd9'})
    assert retired_doc['is_current'] is False
    assert 'retired_at' in retired_doc


def test_scunpacked_sync_empty_upstream_raises_without_retiring(app, sync_mod, monkeypatch):
    monkeypatch.setattr(sync_mod, 'SCUNPACKED_RESOURCES', {
        'mining_deposits': ('mining_deposit_master', 'resources/resources.json', _simple_mapper),
    })
    get_db()['mining_deposit_master'].insert_one({
        '_id': 'existing', 'name': 'Old', 'is_current': True, '_sync': {'run_id': 'previous-run'},
    })
    monkeypatch.setattr(sync_mod, 'fetch_scunpacked_rows', lambda client, path: [])

    from src.scdata import ScDataError
    with pytest.raises(ScDataError, match='0 筆'):
        sync_mod._sync_scunpacked_resource(None, 'mining_deposits', 'new-run', datetime.utcnow())

    doc = get_db()['mining_deposit_master'].find_one({'_id': 'existing'})
    assert doc['is_current'] is True
    assert 'retired_at' not in doc
