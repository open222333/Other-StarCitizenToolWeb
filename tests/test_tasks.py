"""Celery 背景任務的單元測試（直接呼叫函式，不需要 broker）。"""
from datetime import datetime, timedelta
from src.mongo import get_db


def test_cleanup_old_logs_deletes_expired_records():
    from tasks.scheduled import cleanup_old_logs

    db = get_db()
    now = datetime.utcnow()
    db['logs'].insert_many([
        {'username': 'u', 'action': 'old',    'detail': '', 'success': True,
         'created_at': now - timedelta(days=100)},
        {'username': 'u', 'action': 'recent', 'detail': '', 'success': True,
         'created_at': now - timedelta(days=10)},
    ])

    result = cleanup_old_logs(days=90)

    assert result['deleted'] == 1
    assert result['days'] == 90
    assert db['logs'].count_documents({}) == 1


def test_cleanup_old_logs_nothing_to_delete():
    from tasks.scheduled import cleanup_old_logs

    db = get_db()
    db['logs'].insert_one({
        'username': 'u', 'action': 'fresh', 'detail': '', 'success': True,
        'created_at': datetime.utcnow() - timedelta(days=5),
    })

    result = cleanup_old_logs(days=90)
    assert result['deleted'] == 0
    assert db['logs'].count_documents({}) == 1


def test_periodic_health_check_returns_ok():
    from tasks.scheduled import periodic_health_check

    result = periodic_health_check()
    assert result['status'] == 'ok'
    assert 'checked_at' in result
