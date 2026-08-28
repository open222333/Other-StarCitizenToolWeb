"""同步排程（src/models/sync_schedule.py）的 cron 解析與到期判斷測試。

這支測試存在的理由：cron 解析是自己實作的（為了不引入 croniter 依賴），
所以邊界條件必須有測試網。特別是：
  - 時區：cron 以 Asia/Taipei 解讀，DB 時間戳是 naive UTC，兩者差 8 小時
  - 日與星期都有限制時的 OR 語意（crontab(5) 的行為，很多實作會弄錯）
"""
from datetime import datetime

import pytest

from src.models.sync_schedule import (
    DEFAULT_CRON, SyncSchedule, SyncScheduleError, next_run_after, parse_cron,
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
    assert SyncSchedule.validate_cron(cron) is True
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
    assert SyncSchedule.validate_cron(cron) is False
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
#  is_due / 設定存取（需要 DB，用 conftest 的 mongomock）
# ═══════════════════════════════════════════════════════════

def test_get_creates_default(app):
    doc = SyncSchedule.get()
    assert doc['cron'] == DEFAULT_CRON
    assert doc['enabled'] is True
    assert doc['timezone'] == 'Asia/Taipei'


def test_is_due_when_never_run(app):
    assert SyncSchedule.is_due(None) is True


def test_is_due_false_when_disabled(app):
    SyncSchedule.update(enabled=False)
    assert SyncSchedule.is_due(None) is False


def test_is_due_respects_cron(app):
    SyncSchedule.update(cron='30 4 * * *')      # 每天台北 04:30 = UTC 20:30
    last = datetime(2026, 8, 20, 20, 30)        # 剛好在觸發點跑完

    # 隔天觸發點之前 → 還沒到期
    assert SyncSchedule.is_due(last, now=datetime(2026, 8, 21, 12, 0)) is False
    # 隔天觸發點之後 → 到期
    assert SyncSchedule.is_due(last, now=datetime(2026, 8, 21, 20, 31)) is True


def test_update_rejects_bad_cron(app):
    with pytest.raises(SyncScheduleError):
        SyncSchedule.update(cron='not a cron')


def test_update_rejects_unknown_resource(app):
    with pytest.raises(SyncScheduleError):
        SyncSchedule.update(resources=['items', 'spaceships'])


def test_update_rejects_empty_resources(app):
    with pytest.raises(SyncScheduleError):
        SyncSchedule.update(resources=[])


def test_next_run_none_when_disabled(app):
    SyncSchedule.update(enabled=False)
    assert SyncSchedule.next_run() is None
