"""同步排程（src/models/sync_schedule.py）的 cron 解析與到期判斷測試。

這支測試存在的理由：cron 解析是自己實作的（為了不引入 croniter 依賴），
所以邊界條件必須有測試網。特別是：
  - 時區：cron 以 Asia/Taipei 解讀，DB 時間戳是 naive UTC，兩者差 8 小時
  - 日與星期都有限制時的 OR 語意（crontab(5) 的行為，很多實作會弄錯）
"""
from datetime import datetime

import pytest

from src.models.sync_schedule import (
    DEFAULT_CRON, JOB_KEYS, WIKI_JOB_KEYS, SyncJobs, SyncScheduleError, next_run_after, parse_cron,
    validate_cron,
)


# ═══════════════════════════════════════════════════════════
#  欄位解析
# ═══════════════════════════════════════════════════════════

@pytest.mark.parametrize('cron', [
    '30 4 * * 1',        # 每週一 04:30
    '* * * * *',         # 每分鐘
    '*/15 * * * *',      # 每 15 分
    '0 */2 * * *',       # 每 2 小時
    '0 0 1 * *',         # 每月 1 號
    '0 9 * * 1-5',       # 平日 09:00
    '0 9 * * 0',         # 週日
    '0 9 * * 7',         # 7 也是週日
    '5,10,15 * * * *',   # 列舉
    '0-30/10 * * * *',   # 範圍加間隔
    '0 0 29 2 *',        # 閏日
])
def test_valid_cron_accepted(cron):
    assert validate_cron(cron) is True
    parse_cron(cron)


@pytest.mark.parametrize('cron', [
    '',                  # 空字串
    '* * * *',           # 只有 4 欄
    '* * * * * *',       # 6 欄
    '60 * * * *',        # 分鐘超出範圍
    '* 24 * * *',        # 小時超出範圍
    '* * 32 * *',        # 日超出範圍
    '* * * 13 *',        # 月超出範圍
    '* * * * 8',         # 星期超出範圍
    'abc * * * *',       # 非數字
    '*/0 * * * *',       # 間隔 0
    '30-5 * * * *',      # 範圍反了
    '@daily',            # 不支援別名
])
def test_invalid_cron_rejected(cron):
    assert validate_cron(cron) is False
    with pytest.raises(SyncScheduleError):
        parse_cron(cron)


def test_sunday_seven_normalised_to_zero():
    """cron 的星期欄位 0 和 7 都代表週日。"""
    assert parse_cron('0 0 * * 7')[4] == parse_cron('0 0 * * 0')[4] == {0}


# ═══════════════════════════════════════════════════════════
#  下一次觸發時間（含時區）
# ═══════════════════════════════════════════════════════════

def test_next_run_is_interpreted_in_taipei_time():
    """'30 4 * * *' 是台北 04:30，也就是 UTC 20:30（前一天）。

    這正是先前的 bug：舊版直接用 utcnow() 比對，導致實際觸發時間
    比設定頁顯示給使用者的時間晚了 8 小時。
    """
    # 2026-08-20 00:00 UTC = 台北 08:00，所以下一次台北 04:30 是隔天
    after = datetime(2026, 8, 20, 0, 0)
    nxt = next_run_after('30 4 * * *', after)
    # 台北 2026-08-21 04:30 == UTC 2026-08-20 20:30
    assert nxt == datetime(2026, 8, 20, 20, 30)


def test_next_run_weekly_monday():
    """DEFAULT_CRON = 每週一 04:30（台北）→ UTC 週日 20:30。"""
    after = datetime(2026, 8, 20, 0, 0)          # 2026-08-20 是週四
    nxt = next_run_after(DEFAULT_CRON, after)
    assert nxt == datetime(2026, 8, 23, 20, 30)  # UTC 週日 = 台北週一
    assert nxt.weekday() == 6                    # UTC 上看是週日


def test_next_run_every_minute_is_next_minute():
    after = datetime(2026, 8, 20, 10, 15, 30)
    assert next_run_after('* * * * *', after) == datetime(2026, 8, 20, 10, 16)


def test_next_run_step_minutes():
    after = datetime(2026, 8, 20, 10, 7)
    assert next_run_after('*/15 * * * *', after) == datetime(2026, 8, 20, 10, 15)


def test_day_and_weekday_both_set_uses_or():
    """日與星期都不是 * 時是 OR —— 這是 crontab(5) 的行為。"""
    sets = parse_cron('0 0 1 * 5')       # 每月 1 號 或 每週五
    from src.models.sync_schedule import _matches
    assert _matches(datetime(2026, 8, 1), sets)    # 1 號（週六）→ 命中日
    assert _matches(datetime(2026, 8, 7), sets)    # 7 號是週五 → 命中星期
    assert not _matches(datetime(2026, 8, 6), sets)  # 6 號週四 → 都不中


def test_impossible_date_returns_none():
    """2/30 永遠不會發生，不能無限迴圈，要回 None。"""
    assert next_run_after('0 0 30 2 *', datetime(2026, 8, 20)) is None


def test_leap_day_found_within_four_years():
    nxt = next_run_after('0 12 29 2 *', datetime(2026, 8, 20))
    assert nxt is not None
    assert nxt.month == 2 and nxt.day == 29


# ═══════════════════════════════════════════════════════════
#  同步項目設定存取（需要 DB，用 conftest 的 mongomock）
# ═══════════════════════════════════════════════════════════

def test_all_creates_every_job_in_order(app):
    jobs = SyncJobs.all()
    assert [j['key'] for j in jobs] == JOB_KEYS
    assert jobs[0]['key'] == 'translations', '翻譯要最先跑（其他主檔會查中文快照）'
    assert all(j['enabled'] for j in jobs)
    assert SyncJobs.get('items')['cron'] == DEFAULT_CRON
    assert SyncJobs.get('items')['label'] == '物品'


def test_job_keys_match_sync_sources():
    from src.scdata import WIKI_RESOURCES
    assert set(WIKI_JOB_KEYS) == set(WIKI_RESOURCES)
    assert set(JOB_KEYS) == set(WIKI_RESOURCES) | {'translations', 'mining', 'locations', 'uex'}
    from src.scdata import SCUNPACKED_EXTRA, SCUNPACKED_JOBS, SCUNPACKED_RESOURCES
    assert set(SCUNPACKED_EXTRA) <= set(WIKI_RESOURCES), '額外的 scunpacked 資源掛在 Wiki 同步項目後面'
    synced = [r for jobs in (SCUNPACKED_JOBS, SCUNPACKED_EXTRA) for rs in jobs.values() for r in rs]
    assert sorted(synced) == sorted(SCUNPACKED_RESOURCES)


def test_update_job(app):
    job = SyncJobs.update('missions', cron='0 6 * * *', enabled=False, updated_by='admin')
    assert (job['cron'], job['enabled'], job['updated_by']) == ('0 6 * * *', False, 'admin')
    assert SyncJobs.get('items')['cron'] == DEFAULT_CRON, '只改那一項'


def test_update_rejects_bad_cron(app):
    with pytest.raises(SyncScheduleError):
        SyncJobs.update('items', cron='not a cron')


def test_update_rejects_unknown_job(app):
    with pytest.raises(SyncScheduleError):
        SyncJobs.update('spaceships', cron='0 4 * * *')


def test_next_run_none_when_disabled(app):
    assert SyncJobs.next_run(SyncJobs.update('items', enabled=False)) is None
    assert SyncJobs.next_run(SyncJobs.update('items', enabled=True)) is not None


def test_next_run_uses_backoff_after_failure(app):
    from src.mongo import get_db
    finished = datetime(2026, 8, 20, 0, 0)
    SyncJobs.all()
    get_db()['sync_jobs'].update_one({'_id': 'items'}, {'$set': {
        'cron': '30 4 * * 1', 'last_finished_at': finished, 'last_ok': False,
        'consecutive_failures': 1}})
    assert SyncJobs.next_run(SyncJobs.get('items')) == datetime(2026, 8, 20, 0, 30)


def test_seed_migrates_legacy_single_schedule(app):
    """舊版單一排程：沿用 cron／啟用、沒選的資源停用、上次時間取最後一輪紀錄。"""
    from src.mongo import get_db
    db = get_db()
    last = datetime(2026, 9, 1, 12, 0)
    db['sync_schedule'].insert_one({
        '_id': 'default', 'cron': '15 3 * * 2', 'enabled': True, 'with_uex': False,
        'resources': ['items', 'blueprints'], 'resources_custom': True})
    db['sync_runs'].insert_one({'_id': 'r', 'started_at': last, 'finished_at': last, 'ok': True})
    db['item_master'].insert_one({'_id': 'i1', 'is_current': True})    # 舊版同步過的有資料

    jobs = {j['key']: j for j in SyncJobs.all()}
    assert all(j['cron'] == '15 3 * * 2' for j in jobs.values())
    assert jobs['items']['enabled'] and jobs['blueprints']['enabled']
    assert not jobs['vehicles']['enabled'], '舊排程沒選的資源要停用'
    assert not jobs['uex']['enabled'], 'with_uex=False'
    assert jobs['translations']['enabled'] and jobs['mining']['enabled']
    assert jobs['items']['last_finished_at'] == last, '不然部署完全部項目會立刻全量同步'
    assert not jobs['missions'].get('last_finished_at'), '舊版沒同步過（資料庫是空的）的不能借上次時間'


def test_seed_keeps_existing_jobs(app):
    SyncJobs.update('items', cron='0 1 * * *')
    from src.mongo import get_db
    get_db()['sync_jobs'].delete_one({'_id': 'missions'})
    jobs = {j['key']: j for j in SyncJobs.all()}
    assert jobs['items']['cron'] == '0 1 * * *'
    assert jobs['missions']['cron'] == DEFAULT_CRON


def test_empty_database_that_was_never_synced_is_due(app):
    """已經部署過、任務資料庫借到舊的上次時間卻是空的 → 心跳要馬上同步它。"""
    from src.mongo import get_db
    SyncJobs.all()
    now = datetime(2026, 10, 2, 12, 0)
    get_db()['sync_jobs'].update_many({}, {'$set': {'last_finished_at': now, 'last_ok': True}})
    get_db()['item_master'].insert_one({'_id': 'i1', 'is_current': True})
    due = dict(SyncJobs.due_jobs(now=now))
    assert due.get('missions') == 'never_synced'
    assert 'items' not in due, '有資料的照 cron'
    # 新版真的跑過一次之後（有 last_run_id）就照 cron，即使上游真的沒資料
    get_db()['sync_jobs'].update_one({'_id': 'missions'}, {'$set': {'last_run_id': 'r1'}})
    assert 'missions' not in dict(SyncJobs.due_jobs(now=now))
    # 停用的不管
    get_db()['sync_jobs'].update_one({'_id': 'factions'}, {'$set': {'enabled': False}})
    assert 'factions' not in dict(SyncJobs.due_jobs(now=now))
