"""機密值健檢（src/secret_guard.py）的測試。

背景：`.env.default` 與 `conf/config.ini.default` 是公開在版控裡的範本，
裡面的 `admin` / `root_password` / `flask_password` / `redis_password`
等同「沒有密碼」。實際發生過的情況是：ADMIN_PASSWORD 有人記得改，
但 MYSQL / REDIS 的三個一直是範本值 —— 因為沒有任何機制會告訴你。

這支測試鎖住 fail-closed 的行為：範本值一定要被判定為不安全，
而「沒在用的服務留空」不能被誤判成錯誤（本專案不用 MySQL）。
判斷邏輯刻意抽出成純函式就是為了能這樣測 —— run.py 的 top-level
程式碼（gunicorn 的進入點）沒辦法直接測。
"""
import pytest

from src.secret_guard import (
    collect_weak_secrets,
    format_startup_error,
    is_weak_secret,
)


# ── is_weak_secret ────────────────────────────────────────────

@pytest.mark.parametrize('value', [
    'admin',            # .env.default 的 ADMIN_PASSWORD
    'root_password',    # .env.default 的 MYSQL_ROOT_PASSWORD
    'flask_password',   # .env.default 的 MYSQL_PASSWORD
    'redis_password',   # .env.default 的 REDIS_PASSWORD
    'password',
    'changeme',
    '123456',
    '',
])
def test_template_and_common_values_are_weak(value):
    assert is_weak_secret(value) is True


@pytest.mark.parametrize('value', [
    'Admin',            # 大小寫不該用來繞過
    ' admin ',          # 前後空白也不該用來繞過
    'REDIS_PASSWORD'.lower(),
])
def test_case_and_whitespace_do_not_bypass(value):
    assert is_weak_secret(value) is True


@pytest.mark.parametrize('value', [
    'sZ8mQ2vT7hL1xR4bN6kD9wYc',   # 24 碼隨機
    'correct horse battery staple',
    'admin123!',                   # 含範本字串但不等於它
])
def test_real_secrets_are_not_weak(value):
    assert is_weak_secret(value) is False


def test_none_is_weak():
    """讀不到環境變數時會是 None，不該拋例外，要當成「沒設定」。"""
    assert is_weak_secret(None) is True


# ── collect_weak_secrets ──────────────────────────────────────

def test_all_strong_secrets_pass():
    problems = collect_weak_secrets([
        ('ADMIN_PASSWORD', 'sZ8mQ2vT7hL1xR4bN6kD9wYc', True),
        ('REDIS_PASSWORD', 'aB3cD4eF5gH6iJ7kL8mN9oP0', True),
        ('MYSQL_PASSWORD', '', False),
    ])
    assert problems == []


def test_optional_secret_may_be_empty():
    """MySQL 沒在用 —— 留空是正常狀態，不能被當成錯誤。"""
    assert collect_weak_secrets([('MYSQL_PASSWORD', '', False)]) == []
    assert collect_weak_secrets([('MYSQL_PASSWORD', None, False)]) == []


def test_optional_secret_still_rejects_template_value():
    """但一旦填了，就不接受範本值 —— 這正是先前漏掉的那個情況。"""
    problems = collect_weak_secrets([('MYSQL_PASSWORD', 'flask_password', False)])
    assert len(problems) == 1
    assert 'MYSQL_PASSWORD' in problems[0]


def test_required_secret_rejects_empty():
    problems = collect_weak_secrets([('REDIS_PASSWORD', '', True)])
    assert len(problems) == 1
    assert '未設定' in problems[0]


def test_reports_every_problem_not_just_the_first():
    """一次列出全部，不要讓使用者改一個、重啟、再發現下一個。"""
    problems = collect_weak_secrets([
        ('ADMIN_PASSWORD', 'admin', True),
        ('REDIS_PASSWORD', 'redis_password', True),
        ('MYSQL_PASSWORD', 'flask_password', False),
    ])
    assert len(problems) == 3
    joined = '\n'.join(problems)
    for name in ('ADMIN_PASSWORD', 'REDIS_PASSWORD', 'MYSQL_PASSWORD'):
        assert name in joined


def test_error_message_mentions_env_and_every_problem():
    """訊息要能讓人直接知道去哪裡改 —— 這是啟動失敗時唯一的線索。"""
    message = format_startup_error(collect_weak_secrets([
        ('ADMIN_PASSWORD', 'admin', True),
        ('REDIS_PASSWORD', 'redis_password', True),
    ]))
    assert 'ADMIN_PASSWORD' in message
    assert 'REDIS_PASSWORD' in message
    assert '.env' in message
    # 不要把使用者導回 config.ini —— 那個檔案有納入版控
    assert 'config.ini' in message


def test_secrets_are_never_echoed_in_the_error_message():
    """訊息會進 container log，不該把值本身印出來。"""
    message = format_startup_error(
        collect_weak_secrets([('REDIS_PASSWORD', 'redis_password', True)]))
    assert 'redis_password' not in message
