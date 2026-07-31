"""Celery worker / beat 入口。

開發啟動：
  celery -A celery_worker worker --loglevel=info
  celery -A celery_worker beat   --loglevel=info
"""
from src.celery_app import celery_app as app  # noqa: F401  (Celery CLI 自動偵測 `app`)
