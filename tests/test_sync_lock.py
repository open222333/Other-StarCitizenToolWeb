"""同步互斥鎖與到期判斷的測試（tasks/scdata_sync.py）。

這支測試針對的是三個真實缺陷：

1. **沒有鎖 → 併發同步互相把主檔標成已下架。**
   `_sync_wiki_resource` 收尾會 `update_many({'_sync.run_id': {'$ne': run_id}},
   {'$set': {'is_current': False}})`，兩輪並行時 B 會把 A 剛寫的全部下架，
   而所有主檔查詢都過濾 is_current=True → 物品搜尋大面積變空。

2. **只看成功紀錄 → 失敗後每 5 分鐘無限重跑。**
   到期判斷的基準是「最後一次嘗試」（每個同步項目各自記錄），失敗走 backoff。

3. **上游回空清單 → 下架步驟清空整個主檔。**
"""
from datetime import datetime, timedelta

import pytest

from src.models.sync_schedule import SyncJobs
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
#  到期判斷（每個同步項目各自計算，見 src/models/sync_schedule.py 的 SyncJobs）
# ═══════════════════════════════════════════════════════════

def _set_job(key, **fields):
    SyncJobs.all()
    get_db()['sync_jobs'].update_one({'_id': key}, {'$set': fields})
    return SyncJobs.get(key)


def test_due_when_never_run(app):
    assert SyncJobs.is_due(SyncJobs.get('items')) == (True, 'never_run')


def test_not_due_when_disabled(app):
    job = SyncJobs.update('items', enabled=False)
    assert SyncJobs.is_due(job) == (False, 'disabled')


def test_failed_run_is_not_ignored(app):
    """失敗的那一輪也算「嘗試過」——不能 5 分鐘後又立刻重跑。"""
    job = _set_job('items', cron='30 4 * * 1', last_ok=False, consecutive_failures=1,
                   last_finished_at=datetime.utcnow() - timedelta(minutes=5))
    due, reason = SyncJobs.is_due(job)
    assert due is False, '失敗後 5 分鐘就重跑 —— 會變成無限重轟上游'
    assert reason.startswith('failure_backoff')


def test_failed_run_retries_after_backoff(app, sync_mod):
    """失敗後過了 backoff 時間就可以重試，不用等下一個 cron 時段。"""
    job = _set_job('items', cron='30 4 * * 1', last_ok=False, consecutive_failures=1,
                   last_finished_at=datetime.utcnow() - timedelta(minutes=sync_mod.FAILURE_BACKOFF_MIN + 1))
    due, reason = SyncJobs.is_due(job)
    assert due is True
    assert reason.startswith('retry_after_failure')


def test_too_many_failures_falls_back_to_cron(app, sync_mod):
    """連續失敗太多次就回到 cron 節奏，不再每 30 分鐘重試。"""
    job = _set_job('items', cron='30 4 * * 1', last_ok=False,
                   consecutive_failures=sync_mod.MAX_CONSECUTIVE_FAILURES,
                   last_finished_at=datetime(2026, 8, 18, 0, 0))     # 週二（UTC）
    assert SyncJobs.is_due(job, now=datetime(2026, 8, 19, 0, 0)) == (False, 'not_due')
    # 下一個週一 04:30 台北 = 週日 20:30 UTC
    assert SyncJobs.is_due(job, now=datetime(2026, 8, 23, 20, 31)) == (True, 'cron_due')


def test_successful_run_uses_cron(app):
    """成功之後就照 cron 判斷（cron 以台北時間解讀）。"""
    job = _set_job('items', cron='30 4 * * *', last_ok=True,      # 每天台北 04:30 = UTC 20:30
                   last_finished_at=datetime(2026, 8, 20, 20, 30))
    assert SyncJobs.is_due(job, now=datetime(2026, 8, 21, 12, 0)) == (False, 'not_due')
    assert SyncJobs.is_due(job, now=datetime(2026, 8, 21, 20, 31)) == (True, 'cron_due')


def test_jobs_are_scheduled_independently(app):
    """各項目有自己的時間：一項到期不代表其他項目也要跑。"""
    now = datetime(2026, 8, 21, 20, 31)
    for key in SyncJobs.all():
        _set_job(key['key'], cron='30 4 * * 1', last_ok=True, last_finished_at=now, last_run_id='r0')
    _set_job('missions', cron='0 * * * *', last_finished_at=now - timedelta(hours=2))
    _set_job('items', enabled=False, last_finished_at=None)
    assert SyncJobs.due_jobs(now=now) == [('missions', 'cron_due')]


def test_record_result_counts_failures(app):
    now = datetime.utcnow()
    SyncJobs.record_result('items', 'r1', now, now, False, error='boom')
    SyncJobs.record_result('items', 'r2', now, now, False, error='boom')
    assert SyncJobs.get('items')['consecutive_failures'] == 2
    SyncJobs.record_result('items', 'r3', now, now, None, error='略過')   # 略過不算
    assert SyncJobs.get('items')['consecutive_failures'] == 2
    SyncJobs.record_result('items', 'r4', now, now, True)
    job = SyncJobs.get('items')
    assert job['consecutive_failures'] == 0 and job['last_ok'] is True and job['running'] is False


class _FakeAsync:
    """攔下 sync_scdata.apply_async，記下派送了哪些項目（不碰真的 broker）。"""

    def __init__(self):
        self.sent = []

    def __call__(self, kwargs=None, **_):
        self.sent.append(kwargs)

        class _R:
            id = f'task-{len(self.sent)}'
        return _R()


def test_heartbeat_dispatches_each_due_job_separately(app, sync_mod, monkeypatch):
    """到期的項目各自派成一個任務（可以同時跑），不是在心跳裡依序跑完。"""
    fake = _FakeAsync()
    monkeypatch.setattr(sync_mod, '_translations_bootstrap', lambda: None)
    monkeypatch.setattr(sync_mod.sync_scdata, 'apply_async', fake)
    now = datetime.utcnow()
    for job in SyncJobs.all():
        _set_job(job['key'], last_ok=True, last_finished_at=now, last_run_id='r0')
    _set_job('missions', last_finished_at=None)
    _set_job('translations', last_finished_at=None)

    result = sync_mod.check_and_run_scheduled_sync()
    assert result['dispatched'] == ['translations', 'missions']
    assert fake.sent == [{'jobs': ['translations']}, {'jobs': ['missions']}]
    assert SyncJobs.get('missions')['queued'] is True

    # 下一次心跳：已在排隊的不重複派送
    result = sync_mod.check_and_run_scheduled_sync()
    assert result['dispatched'] == [] and len(fake.sent) == 2


def test_dispatch_skips_running_and_stale_queue_is_redispatched(app, sync_mod, monkeypatch):
    fake = _FakeAsync()
    monkeypatch.setattr(sync_mod.sync_scdata, 'apply_async', fake)
    with sync_mod.sync_lock('other-task', sync_mod.job_lock_key('items')):
        sent, skipped = sync_mod.dispatch_jobs(['items', 'vehicles'])
    assert (sent, skipped) == (['vehicles'], ['items'])

    # 排隊太久還沒開始（worker 重啟、佇列被清掉）→ 可以重新派送
    _set_job('vehicles', queued_at=datetime.utcnow() - timedelta(minutes=sync_mod.SyncJobs and 61))
    sent, _ = sync_mod.dispatch_jobs(['vehicles'])
    assert sent == ['vehicles']


def test_job_locks_are_per_job(app, sync_mod):
    """不同項目可以同時拿到鎖；同一項不行。"""
    with sync_mod.sync_lock('A', sync_mod.job_lock_key('items')) as a, \
            sync_mod.sync_lock('B', sync_mod.job_lock_key('missions')) as b, \
            sync_mod.sync_lock('C', sync_mod.job_lock_key('items')) as c:
        assert (a, b, c) == (True, True, False)
        assert sync_mod.running_jobs() == ['items', 'missions']
        assert sync_mod.is_sync_running() is True
    assert sync_mod.running_jobs() == [] and sync_mod.is_sync_running() is False


def test_do_sync_skips_job_already_running(app, sync_mod, monkeypatch):
    ran = []
    monkeypatch.setattr(sync_mod, '_run_job',
                        lambda key, *a: ran.append(key) or ([], [], True))
    with sync_mod.sync_lock('other-task', sync_mod.job_lock_key('items')):
        result = sync_mod._do_sync(jobs=['items', 'missions'])
    assert ran == ['missions']
    assert result['jobs'] == ['missions'] and result['busy'] == ['items']

    with sync_mod.sync_lock('other-task', sync_mod.job_lock_key('items')):
        result = sync_mod._do_sync(jobs=['items'])
    assert result == {'skipped': True, 'reason': 'already_running', 'jobs': ['items'], 'busy': ['items']}


def test_progress_is_reported_while_running(app, sync_mod, monkeypatch):
    """跑的時候把進度寫進 sync_jobs，結束後清掉。"""
    seen_progress = []
    monkeypatch.setattr(sync_mod, 'PROGRESS_INTERVAL_S', 0)
    monkeypatch.setattr(sync_mod, 'wiki_rows', lambda client, resource: iter(
        [{'uuid': f'u{i}', 'name': f'Item {i}'} for i in range(3)]))

    real_set = SyncJobs.set_progress

    def spy(key, progress):
        seen_progress.append((key, dict(progress)))
        real_set(key, progress)
    monkeypatch.setattr(SyncJobs, 'set_progress', staticmethod(spy))

    sync_mod._do_sync(jobs=['items'])
    assert seen_progress[0][1]['phase'].startswith('讀取')
    assert any(p.get('seen') == 3 for _, p in seen_progress)
    job = SyncJobs.get('items')
    assert job['progress'] == {} and job['running'] is False and job['last_ok'] is True


def test_do_sync_records_each_job(app, sync_mod, monkeypatch):
    """每一項各自記錄結果：一項失敗不影響其他項目的狀態。"""
    def fake_run(key, run_id, stamp, clients):
        if key == 'missions':
            return [], ['missions: boom'], False
        if key == 'uex':
            return [], ['uex: 未設定 UEX_API_TOKEN，略過'], None
        return [{'resource': key, 'seen': 3, 'written': 2, 'retired': 0}], [], True
    monkeypatch.setattr(sync_mod, '_run_job', fake_run)

    result = sync_mod._do_sync(jobs=['uex', 'missions', 'items'])
    assert result['jobs'] == ['items', 'missions', 'uex'], '要照固定順序跑'
    assert result['ok'] is False and result['errors'] == ['missions: boom']
    assert SyncJobs.get('items')['last_ok'] is True
    assert SyncJobs.get('items')['last_stats'] == {'seen': 3, 'written': 2, 'retired': 0}
    assert SyncJobs.get('missions')['last_ok'] is False
    assert SyncJobs.get('uex')['last_ok'] is None, '沒有 token 是略過，不是失敗'
    run = get_db()['sync_runs'].find_one({'_id': result['run_id']})
    assert run['jobs'] == ['items', 'missions', 'uex'] and run['skipped_jobs'] == ['uex']


def test_do_sync_rejects_unknown_job(app, sync_mod):
    with pytest.raises(ValueError):
        sync_mod._do_sync(jobs=['spaceships'])


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
