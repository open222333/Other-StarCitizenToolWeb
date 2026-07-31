from celery.schedules import crontab

timezone = 'Asia/Taipei'

beat_schedule = {
    # 每天凌晨 3:00 清除 90 天前的操作日誌
    'cleanup-old-logs-daily': {
        'task': 'tasks.scheduled.cleanup_old_logs',
        'schedule': crontab(hour=3, minute=0),
        'kwargs': {'days': 90},
    },
    # 每 60 秒確認 MongoDB 連線正常
    'periodic-health-check': {
        'task': 'tasks.scheduled.periodic_health_check',
        'schedule': 60.0,
    },
}
