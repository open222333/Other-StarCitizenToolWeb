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
    # 每天凌晨 4:30 同步星際公民遊戲主檔（items / vehicles / commodities + UEX）
    # 遊戲改版後不必等排程，可手動觸發：
    #   docker compose exec worker python -c \
    #     "from tasks.scdata_sync import sync_scdata; print(sync_scdata())"
    'scdata-sync-daily': {
        'task': 'tasks.scdata_sync.sync_scdata',
        'schedule': crontab(hour=4, minute=30),
    },
}

# 全量同步約 130 次外部請求、5～10 分鐘，給足時間上限避免被中途砍掉
task_time_limit = 3600
task_soft_time_limit = 3300
