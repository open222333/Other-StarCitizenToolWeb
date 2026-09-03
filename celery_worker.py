"""Celery worker / beat 入口。

開發啟動：
  celery -A celery_worker worker --loglevel=info
  celery -A celery_worker beat   --loglevel=info
"""
from src import MYSQL_PASSWORD, REDIS_PASSWORD
from src.secret_guard import collect_weak_secrets, format_startup_error

# fail-closed：跟 run.py 同一套檢查。worker / beat 不會經過 run.py，
# 少了這段的話「.env 還是範本密碼」在這兩個容器裡只會表現為
# 連不上 Redis 的重試 log，很難聯想到是密碼沒改。
# ADMIN_PASSWORD 不在這裡檢查 —— 那是 run.py 建立後台帳號時才用得到的。
_problems = collect_weak_secrets([
    ('REDIS_PASSWORD', REDIS_PASSWORD, True),
    ('MYSQL_PASSWORD', MYSQL_PASSWORD, False),
])
if _problems:
    raise SystemExit(format_startup_error(_problems))

from src.celery_app import celery_app as app  # noqa: E402,F401  (Celery CLI 自動偵測 `app`)
