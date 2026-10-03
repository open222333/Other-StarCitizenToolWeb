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
    # 星際公民遊戲資料的實際排程已經搬到 DB（src/models/sync_schedule.py，
    # sync_jobs collection，每個資料庫一筆），可在後台「資料同步排程」頁個別編輯
    # cron。這裡只留一個每 5 分鐘的心跳，去問「哪幾項到期了」，
    # 真正決定要不要跑的邏輯在 tasks.scdata_sync.check_and_run_scheduled_sync。
    #
    # 遊戲改版後不必等排程，可手動觸發：
    #   docker compose exec worker python -c \
    #     "from tasks.scdata_sync import sync_scdata; print(sync_scdata())"
    'check-sync-schedule': {
        'task': 'tasks.scdata_sync.check_and_run_scheduled_sync',
        'schedule': crontab(minute='*/5'),
    },
}

# 每個 worker process 一次只先拿一個任務：同步任務一跑好幾分鐘，預設的
# prefetch（4 個）會讓任務卡在忙碌的 process 後面排隊，旁邊閒著的 process 拿不到，
# 「不同資料庫同時同步」就變成假的。
worker_prefetch_multiplier = 1

# 全量同步約 130 次外部請求、5～10 分鐘，給足時間上限避免被中途砍掉
task_time_limit = 3600
task_soft_time_limit = 3300
