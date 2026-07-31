import logging
from datetime import datetime, timedelta

from src.celery_app import celery_app
from src.mongo import get_db

logger = logging.getLogger(__name__)


@celery_app.task(name='tasks.scheduled.cleanup_old_logs', bind=True, max_retries=3)
def cleanup_old_logs(self, days: int = 90):
    """刪除 N 天前的操作日誌。"""
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = get_db()['logs'].delete_many({'created_at': {'$lt': cutoff}})
        logger.info('cleanup_old_logs: deleted %d records older than %d days', result.deleted_count, days)
        return {'deleted': result.deleted_count, 'days': days}
    except Exception as exc:
        logger.error('cleanup_old_logs failed: %s', exc)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name='tasks.scheduled.periodic_health_check')
def periodic_health_check():
    """確認 MongoDB 連線正常。"""
    try:
        get_db().command('ping')
        return {'status': 'ok', 'checked_at': datetime.utcnow().isoformat()}
    except Exception as exc:
        logger.error('health_check failed: %s', exc)
        return {'status': 'error', 'error': str(exc)}
