"""同步互斥鎖與到期判斷的測試（tasks/scdata_sync.py）。

這支測試針對的是三個真實缺陷：

1. **沒有鎖 → 併發同步互相把主檔標成已下架。**
   `_sync_wiki_resource` 收尾會 `update_many({'_sync.run_id': {'$ne': run_id}},
   {'$set': {'is_current': False}})`，兩輪並行時 B 會把 A 剛寫的全部下架，
   而所有主檔查詢都過濾 is_current=True → 物品搜尋大面積變空。

2. **只看成功紀錄 → 失敗後每 5 分鐘無限重跑。**
   任何一個資源或 UEX endpoint 失敗就 ok=False，舊版 `find_one({'ok': True})`
   讓這輪完全不算，5 分鐘後又判定到期。

3. **上游回空清單 → 下架步驟清空整個主檔。**
"""
from datetime import datetime, timedelta

import pytest

from src.models.sync_schedule import SyncSchedule
from src.mongo import get_db


@pytest.fixture
def sync_mod():
    import tasks.scdata_sync as m
    return m


# ═══════════════════════════════════════════════════════════
#  互斥鎖
# ═══════════════════════════════════════════════════════════

def test_lock_is_exclusive(sync_mod):
    """第一個拿到鎖，第二個必須拿不到。"""
    with sync_mod.sync_lock('run-A') as first:
        assert first is True
        with sync_mod.sync_lock('run-B') as second:
            assert second is False, '兩輪同步同時拿到鎖 —— 會互相把主檔標成已下架'


def test_lock_released_after_block(sync_mod):
    """離開 with 之後鎖要放掉，下一輪才拿得到。"""
    with sync_mod.sync_lock('run-A') as ok:
        assert ok is True
    with sync_mod.sync_lock('run-B') as ok:
        assert ok is True


def test_lock_released_even_on_exception(sync_mod):
    """同步中途炸掉也要解鎖，不然要等一小時 TTL。"""
    with pytest.raises(RuntimeError):
        with sync_mod.sync_lock('run-A') as ok:
            assert ok is True
            raise RuntimeError('同步爆了')

    with sync_mod.sync_lock('run-B') as ok:
        assert ok is True, '例外發生後鎖沒有釋放'


def test_unlock_only_removes_own_lock(sync_mod):
    """A 的鎖 TTL 過期、B 取得鎖之後，A 結束時不能刪掉 B 的鎖。"""
    from src.redis_client import get_redis
    redis = get_redis()

    with sync_mod.sync_lock('run-A') as ok:
        assert ok is True
        # 模擬 A 的鎖過期、B 搶到鎖
        redis.set(sync_mod.SYNC_LOCK_KEY, 'run-B')
    # A 離開 with → 應該不動 B 的鎖
    assert redis.get(sync_mod.SYNC_LOCK_KEY) == 'run-B', 'A 誤刪了 B 的鎖'


def test_lock_survives_redis_failure(sync_mod, monkeypatch):
    """Redis 掛掉時選擇放行（同步比鎖重要），不能整個同步停擺。"""
    def boom():
        raise ConnectionError('redis down')
    monkeypatch.setattr(sync_mod, 'get_redis', boom)

    with sync_mod.sync_lock('run-A') as ok:
        assert ok is True, 'Redis 不可用時應該放行而不是擋住同步'


# ═══════════════════════════════════════════════════════════
#  到期判斷
# ═══════════════════════════════════════════════════════════

def _insert_run(ok, finished_at, started_at=None):
    get_db()['sync_runs'].insert_one({
        '_id': f'run-{finished_at.isoformat()}-{ok}',
        'started_at': started_at or finished_at,
        'finished_at': finished_at,
        'ok': ok,
        'errors': [] if ok else ['boom'],
        'stats': [],
    })


def test_due_when_never_run(app, sync_mod):
    due, reason = sync_mod._is_due()
    assert due is True
    assert reason == 'never_run'


def test_not_due_when_disabled(app, sync_mod):
    SyncSchedule.update(enabled=False)
    due, reason = sync_mod._is_due()
    assert due is False
    assert reason == 'disabled'


def test_failed_run_is_not_ignored(app, sync_mod):
    """失敗的那一輪也算「嘗試過」——不能 5 分鐘後又立刻重跑。

    舊版用 find_one({'ok': True})，失敗的紀錄看不見 → 永遠判定到期。
    """
    SyncSchedule.update(cron='30 4 * * 1')          # 每週一，離現在很遠
    _insert_run(ok=False, finished_at=datetime.utcnow() - timedelta(minutes=5))

    due, reason = sync_mod._is_due()
    assert due is False, '失敗後 5 分鐘就重跑 —— 會變成無限重轟上游'
    assert reason.startswith('failure_backoff')


def test_failed_run_retries_after_backoff(app, sync_mod):
    """失敗後過了 backoff 時間就可以重試，不用等下一個 cron 時段。"""
    SyncSchedule.update(cron='30 4 * * 1')
    _insert_run(
        ok=False,
        finished_at=datetime.utcnow()
        - timedelta(minutes=sync_mod.FAILURE_BACKOFF_MIN + 1),
    )

    due, reason = sync_mod._is_due()
    assert due is True
    assert reason.startswith('retry_after_failure')


def test_too_many_failures_falls_back_to_cron(app, sync_mod):
    """連續失敗太多次就回到 cron 節奏，不再每 30 分鐘重試。"""
    SyncSchedule.update(cron='30 4 * * 1')
    base = datetime.utcnow() - timedelta(hours=10)
    for i in range(sync_mod.MAX_CONSECUTIVE_FAILURES):
        _insert_run(ok=False, finished_at=base + timedelta(minutes=i * 40))

    due, reason = sync_mod._is_due()
    # 上一輪在 10 小時前，週一的 cron 還沒到 → 不該跑
    assert due is False
    assert reason == 'not_due'


def test_consecutive_failures_counts_only_leading_run(app, sync_mod):
    """連續失敗次數只數「最新往回」那一段，中間有成功就歸零。"""
    base = datetime.utcnow() - timedelta(hours=5)
    _insert_run(ok=False, finished_at=base)
    _insert_run(ok=True, finished_at=base + timedelta(minutes=10))
    _insert_run(ok=False, finished_at=base + timedelta(minutes=20))

    assert sync_mod._consecutive_failures() == 1


def test_successful_run_uses_cron(app, sync_mod):
    """成功之後就照 cron 判斷。"""
    SyncSchedule.update(cron='30 4 * * *')          # 每天台北 04:30 = UTC 20:30
    _insert_run(ok=True, finished_at=datetime(2026, 8, 20, 20, 30))

    # 用 SyncSchedule.is_due 直接驗證（_is_due 用 utcnow，不方便注入）
    assert SyncSchedule.is_due(datetime(2026, 8, 20, 20, 30),
                               now=datetime(2026, 8, 21, 12, 0)) is False
    assert SyncSchedule.is_due(datetime(2026, 8, 20, 20, 30),
                               now=datetime(2026, 8, 21, 20, 31)) is True


# ═══════════════════════════════════════════════════════════
#  空清單保護
# ═══════════════════════════════════════════════════════════

def test_empty_upstream_does_not_retire_everything(app, sync_mod, monkeypatch):
    """上游回 0 筆時必須拋錯，不能執行下架步驟。

    否則一次失敗的抓取就會把整個 item_master 標成 is_current=False，
    而所有查詢都過濾 is_current=True → 物品搜尋、庫存 join 全部變空。
    """
    from src.scdata import ScDataError

    db = get_db()
    # 先放一筆「現有」物品，模擬已經同步過的主檔
    db['item_master'].insert_one({
        '_id': 'existing-uuid', 'name': 'Old Item',
        'is_current': True, '_sync': {'run_id': 'previous-run'},
    })

    monkeypatch.setattr(sync_mod, 'wiki_rows', lambda client, resource: iter([]))

    with pytest.raises(ScDataError, match='0 筆'):
        sync_mod._sync_wiki_resource(None, 'items', 'new-run', datetime.utcnow())

    doc = db['item_master'].find_one({'_id': 'existing-uuid'})
    assert doc['is_current'] is True, '上游回空清單時把既有主檔全部下架了'
    assert 'retired_at' not in doc


def test_version_snapshot_drops_raw(app, sync_mod, monkeypatch):
    """版本快照不該複製 raw —— 那會讓 *_versions 長成主檔的 10–20 倍。"""
    db = get_db()
    monkeypatch.setattr(sync_mod, 'wiki_rows', lambda client, resource: iter([
        {'uuid': 'u1', 'name': 'Item One'},
    ]))
    monkeypatch.setattr(sync_mod, 'WIKI_RESOURCES', {
        'items': ('item_master', lambda row: {
            '_id': row['uuid'], 'name': row['name'],
            'game_version': '4.9', 'raw': {'huge': 'x' * 1000},
        }),
    })

    sync_mod._sync_wiki_resource(None, 'items', 'run-1', datetime.utcnow())

    snapshot = db['item_master_versions'].find_one({'_id': 'u1@4.9'})
    assert snapshot is not None
    assert 'raw' not in snapshot, '版本快照仍帶著 raw'
    # 主檔本身要保留 raw
    assert 'raw' in db['item_master'].find_one({'_id': 'u1'})
