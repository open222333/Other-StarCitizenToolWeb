"""遊戲資料同步排程（DB 版，取代 celeryconfig.py 寫死的 cron）。

每個資料庫（翻譯、物品、載具、商品、藍圖、勢力、任務、礦物、地點、UEX 價格）是一個
「同步項目」，各自有自己的 cron、啟用狀態與上次執行結果，存在 `sync_jobs`
collection（一個項目一筆，_id = 項目 key，見下方 SyncJobs）。後台「資料同步排程」
頁可以個別改時間、個別手動同步。

實際觸發邏輯在 tasks/scdata_sync.py 的 check_and_run_scheduled_sync，由
celeryconfig.py 的 5 分鐘心跳呼叫，每次挑出到期的項目一起跑（全域鎖保證同一時間
只有一輪）。

舊版是單一排程（`sync_schedule` collection 的 default 文件），第一次讀取 sync_jobs
時會沿用它的 cron／啟用狀態建立各項目（見 SyncJobs._seed）。

## 時區

cron 一律以 **SCHEDULE_TZ（Asia/Taipei）** 解讀，跟 celeryconfig.py 的
`timezone = 'Asia/Taipei'` 以及後台設定頁顯示給使用者的說明一致。
資料庫裡的時間戳記則沿用專案慣例，全部是 naive UTC。

## 為什麼自己解析 cron 而不用 croniter

排程只需要兩個功能：驗證字串合法、算「某個時間點之後的下一次觸發」。
標準 5 欄位 cron 的語法很小，自己實作約 60 行，換來的是不必為了這個功能
多一個 pip 依賴 —— 而 src/ 是 bind mount、site-packages 不是，所以多一個
依賴就等於「每次部署都要重 build image」。這個取捨對本專案划算。

支援的語法：`*`、`5`、`1-5`、`*/15`、`1-30/5`、`1,3,5`，以及星期的
`0` 與 `7` 都代表週日。不支援 `@daily` 這類別名與 `L`/`W`/`#` 等擴充語法。
"""

from datetime import datetime, timedelta, timezone

from src.mongo import get_db

_DEFAULT_ID = 'default'

DEFAULT_CRON = '30 4 * * 1'  # 每週一 04:30（台北時間）

# cron 的解讀時區，跟 tasks/celeryconfig.py 的 timezone 一致。
#
# 這裡刻意用「固定偏移」而不是 zoneinfo.ZoneInfo('Asia/Taipei')：
#   1. python:*-slim 這類精簡 image 不保證裝了 tzdata，ZoneInfo 會在
#      import 階段就丟 ZoneInfoNotFoundError，讓整個 app 起不來
#   2. 台灣 1979 年之後就沒有日光節約時間，UTC+8 是常數
#      （已驗證 1980–2035 年間偏移恆為 +8:00），所以固定偏移完全等價
# 若日後要支援其他時區，才需要改用 ZoneInfo 並在 Dockerfile 補 tzdata。
SCHEDULE_TZ = timezone(timedelta(hours=8), 'Asia/Taipei')

# 每個欄位的合法範圍：(最小值, 最大值)
_FIELD_RANGES = (
    (0, 59),   # 分
    (0, 23),   # 時
    (1, 31),   # 日
    (1, 12),   # 月
    (0, 6),    # 星期（0 = 週日；輸入的 7 會被正規化成 0）
)


class SyncScheduleError(Exception):
    pass


# ═══════════════════════════════════════════════════════════
#  cron 解析
# ═══════════════════════════════════════════════════════════

def _parse_field(spec: str, index: int) -> set:
    """把單一欄位（例如 '*/15' 或 '1-5'）展開成合法值的集合。"""
    low, high = _FIELD_RANGES[index]
    values: set = set()

    for part in spec.split(','):
        part = part.strip()
        if not part:
            raise SyncScheduleError(f'空的欄位值：{spec!r}')

        step = 1
        if '/' in part:
            part, _, step_raw = part.partition('/')
            if not step_raw.isdigit() or int(step_raw) < 1:
                raise SyncScheduleError(f'無效的間隔值：{step_raw!r}')
            step = int(step_raw)

        if part == '*':
            start, end = low, high
        elif '-' in part.lstrip('-'):
            start_raw, _, end_raw = part.partition('-')
            start, end = _to_int(start_raw, index), _to_int(end_raw, index)
            if start > end:
                raise SyncScheduleError(f'範圍起點大於終點：{part!r}')
        else:
            start = end = _to_int(part, index)

        values.update(range(start, end + 1, step))

    if not values:
        raise SyncScheduleError(f'欄位沒有任何合法值：{spec!r}')
    return values


def _to_int(raw: str, index: int) -> int:
    raw = raw.strip()
    if not raw.isdigit():
        raise SyncScheduleError(f'不是數字：{raw!r}')
    value = int(raw)
    low, high = _FIELD_RANGES[index]

    # 星期允許 7 代表週日，正規化成 0（跟 crontab(5) 的行為一致）
    if index == 4 and value == 7:
        value = 0
    if not (low <= value <= high):
        raise SyncScheduleError(f'{value} 超出合法範圍 {low}-{high}')
    return value


def parse_cron(cron: str) -> tuple:
    """把 5 欄位 cron 字串展開成 (分, 時, 日, 月, 星期) 五個集合。"""
    fields = str(cron or '').split()
    if len(fields) != 5:
        raise SyncScheduleError(
            f'cron 必須是 5 個欄位（分 時 日 月 星期），收到 {len(fields)} 個')
    return tuple(_parse_field(f, i) for i, f in enumerate(fields))


def _matches(moment: datetime, sets: tuple) -> bool:
    """判斷某個時間點是否符合 cron。

    日與星期都不是 `*` 時採 OR（符合任一即成立），這是 crontab(5) 的行為。
    """
    minutes, hours, days, months, weekdays = sets
    if moment.minute not in minutes or moment.hour not in hours:
        return False
    if moment.month not in months:
        return False

    # Python 的 weekday()：週一=0…週日=6；cron 是週日=0…週六=6
    dow = (moment.weekday() + 1) % 7
    day_restricted = days != set(range(1, 32))
    dow_restricted = weekdays != set(range(0, 7))

    if day_restricted and dow_restricted:
        return moment.day in days or dow in weekdays
    if day_restricted:
        return moment.day in days
    if dow_restricted:
        return dow in weekdays
    return True


def validate_cron(cron: str) -> bool:
    try:
        parse_cron(cron)
        return True
    except SyncScheduleError:
        return False


def next_run_after(cron: str, after: datetime) -> datetime | None:
    """回傳 `after` 之後的下一次觸發時間（naive UTC，與 DB 時間戳一致）。

    `after` 也是 naive UTC。找不到（例如 2/30 這種永遠不成立的組合）回 None。
    """
    sets = parse_cron(cron)

    local = after.replace(tzinfo=timezone.utc).astimezone(SCHEDULE_TZ)
    # 從下一整分開始逐分鐘檢查
    cursor = local.replace(second=0, microsecond=0) + timedelta(minutes=1)

    # 上限四年，足以涵蓋閏年造成的 2/29 週期
    limit = cursor + timedelta(days=366 * 4)
    while cursor <= limit:
        if _matches(cursor, sets):
            return cursor.astimezone(timezone.utc).replace(tzinfo=None)
        # 當天完全不可能符合就直接跳一天，避免逐分鐘掃四年
        if cursor.month not in sets[3] or not _matches(
                cursor.replace(hour=0, minute=0), (sets[0] | {0}, sets[1] | {0},
                                                   sets[2], sets[3], sets[4])):
            cursor = (cursor + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        cursor += timedelta(minutes=1)
    return None


# ═══════════════════════════════════════════════════════════
#  同步項目（每個資料庫一筆，各自排程）
# ═══════════════════════════════════════════════════════════

#: 同步項目：(key, 顯示名稱, 預設 cron)。順序就是「同一次心跳有好幾項到期時」
#: 的執行順序——翻譯排第一，因為其他主檔同步時會順便從翻譯資料庫查中文快照。
SYNC_JOBS = [
    ('translations', '翻譯', '0 4 * * 1'),
    ('items', '物品', DEFAULT_CRON),
    ('vehicles', '載具', DEFAULT_CRON),
    ('commodities', '商品', DEFAULT_CRON),
    ('blueprints', '藍圖', DEFAULT_CRON),
    ('factions', '勢力', DEFAULT_CRON),
    ('missions', '任務', DEFAULT_CRON),
    ('mining', '礦物', DEFAULT_CRON),
    ('locations', '地點', DEFAULT_CRON),
    ('uex', 'UEX 價格', DEFAULT_CRON),
]
JOB_KEYS = [k for k, _, _ in SYNC_JOBS]
JOB_LABELS = {k: label for k, label, _ in SYNC_JOBS}
_JOB_DEFAULT_CRON = {k: cron for k, _, cron in SYNC_JOBS}

#: Wiki API 的資源（跟 src/scdata.py 的 WIKI_RESOURCES 一致）
WIKI_JOB_KEYS = ['items', 'vehicles', 'commodities', 'blueprints', 'factions', 'missions']

# 失敗後的重試節奏：上游社群 API 常態性不穩，失敗不要等到下一個 cron 時段
# （可能是一週後），但也不能每 5 分鐘就重轟一次。連續失敗這麼多次就回到
# 正常 cron 節奏，避免上游長期掛掉時無限重試。
FAILURE_BACKOFF_MIN = 30
MAX_CONSECUTIVE_FAILURES = 5

# 派送後多久還沒開始跑，就當成那個任務已經不見了（worker 重啟、佇列被清掉），
# 下次心跳可以重新派送
QUEUE_STALE_MIN = 60


def order_jobs(keys) -> list:
    """去重、丟掉不認得的 key，並照 SYNC_JOBS 的順序排好。"""
    wanted = set(keys or [])
    return [k for k in JOB_KEYS if k in wanted]


class SyncJobs:
    """各同步項目的排程設定與上次執行結果（collection `sync_jobs`，_id = key）。

    欄位：
      cron / enabled / updated_at / updated_by        排程設定（後台可改）
      last_started_at / last_finished_at / last_ok /
      last_error / last_run_id / last_stats /
      consecutive_failures                            上次執行結果（同步時寫入）
      running / running_since / progress / progress_at  這項正在跑、跑到哪（搭配該項的鎖判斷）
      queued / queued_at / queued_task_id / queued_by    已派送、等 worker 接手

    心跳（tasks/scdata_sync.py 的 check_and_run_scheduled_sync）每 5 分鐘把到期的
    項目挑出來一起跑；手動同步可以只跑其中幾項。
    """

    COLLECTION = 'sync_jobs'
    LEGACY_COLLECTION = 'sync_schedule'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def _seed(cls, existing_ids: set):
        """補上還沒有文件的項目。

        第一次建立時沿用舊版單一排程（sync_schedule collection）的 cron／啟用狀態，
        上次完成時間取舊的最後一輪同步紀錄——不然部署完所有項目都會被當成
        「從沒跑過」立刻全量同步一次。之後新增的項目（新的資料庫）用預設值。
        """
        missing = [k for k in JOB_KEYS if k not in existing_ids]
        if not missing:
            return
        db = get_db()
        legacy = db[cls.LEGACY_COLLECTION].find_one({'_id': _DEFAULT_ID}) or {}
        last_run = db['sync_runs'].find_one(
            {'translations_only': {'$ne': True}}, sort=[('started_at', -1)]) if legacy else None
        now = datetime.utcnow()

        for key in missing:
            doc = {
                '_id': key,
                'cron': _JOB_DEFAULT_CRON[key],
                'enabled': True,
                'updated_at': now,
                'updated_by': None,
                'consecutive_failures': 0,
            }
            if legacy:
                doc['cron'] = legacy.get('cron') or doc['cron']
                enabled = legacy.get('enabled', True)
                if key == 'uex':
                    enabled = enabled and legacy.get('with_uex', True)
                elif key in WIKI_JOB_KEYS and legacy.get('resources_custom'):
                    enabled = enabled and key in (legacy.get('resources') or [])
                doc['enabled'] = bool(enabled)
                # 只有舊版真的同步過、資料庫裡有資料的項目才沿用上次時間
                if last_run and last_run.get('finished_at') and cls.has_data(key):
                    doc['last_finished_at'] = last_run['finished_at']
                    doc['last_started_at'] = last_run.get('started_at')
                    doc['last_ok'] = True
            cls._col().update_one({'_id': key}, {'$setOnInsert': doc}, upsert=True)

    @classmethod
    def all(cls) -> list:
        """全部項目（照 SYNC_JOBS 順序），每筆附 label。沒有的會先建立。"""
        docs = {d['_id']: d for d in cls._col().find({'_id': {'$in': JOB_KEYS}})}
        if len(docs) < len(JOB_KEYS):
            cls._seed(set(docs))
            docs = {d['_id']: d for d in cls._col().find({'_id': {'$in': JOB_KEYS}})}
        out = []
        for key in JOB_KEYS:
            doc = docs.get(key) or {'_id': key, 'cron': _JOB_DEFAULT_CRON[key], 'enabled': True}
            doc['key'] = key
            doc['label'] = JOB_LABELS[key]
            out.append(doc)
        return out

    @classmethod
    def get(cls, key: str) -> dict | None:
        if key not in JOB_KEYS:
            return None
        return next(j for j in cls.all() if j['key'] == key)

    @classmethod
    def update(cls, key: str, cron=None, enabled=None, updated_by=None) -> dict:
        """改某一項的排程（cron 會先驗證）。"""
        if key not in JOB_KEYS:
            raise SyncScheduleError(f'不支援的同步項目：{key}')
        fields: dict = {}
        if cron is not None:
            cron = str(cron).strip()
            try:
                parse_cron(cron)
            except SyncScheduleError as err:
                raise SyncScheduleError(f'無效的 cron 表達式：{cron}（{err}）') from None
            fields['cron'] = cron
        if enabled is not None:
            fields['enabled'] = bool(enabled)
        cls.all()   # 確保文件存在
        if fields:
            fields['updated_at'] = datetime.utcnow()
            fields['updated_by'] = updated_by
            cls._col().update_one({'_id': key}, {'$set': fields})
        return cls.get(key)

    # ── 到期判斷 ───────────────────────────────────────────────

    @staticmethod
    def next_run(job: dict, after: datetime = None) -> datetime | None:
        """這一項的下一次預定執行時間（naive UTC）；停用或 cron 無效回 None。

        基準是「上次完成時間」（沒跑過就是現在）——跟 is_due 的判斷一致。
        """
        if not job.get('enabled', True):
            return None
        base = after or job.get('last_finished_at') or datetime.utcnow()
        try:
            nxt = next_run_after(job.get('cron') or DEFAULT_CRON, base)
        except SyncScheduleError:
            return None
        if job.get('last_ok') is False and job.get('last_finished_at') \
                and (job.get('consecutive_failures') or 0) < MAX_CONSECUTIVE_FAILURES:
            retry = job['last_finished_at'] + timedelta(minutes=FAILURE_BACKOFF_MIN)
            nxt = min(nxt, retry) if nxt else retry
        return nxt

    @staticmethod
    def is_due(job: dict, now: datetime = None) -> tuple:
        """回傳 (是否到期, 原因)。

        ⚠️ 基準是「最後一次**嘗試**」而不是「最後一次成功」——只看成功的話，
        一失敗就會每 5 分鐘被判定到期，變成無限重跑。失敗後走較短的 backoff，
        連續失敗太多次就回到 cron 節奏。
        """
        if not job.get('enabled', True):
            return False, 'disabled'
        last = job.get('last_finished_at')
        if not last:
            return True, 'never_run'
        now = now or datetime.utcnow()

        if job.get('last_ok') is False:
            fails = job.get('consecutive_failures') or 0
            if fails < MAX_CONSECUTIVE_FAILURES:
                if now >= last + timedelta(minutes=FAILURE_BACKOFF_MIN):
                    return True, f'retry_after_failure({fails})'
                return False, f'failure_backoff({fails})'

        try:
            nxt = next_run_after(job.get('cron') or DEFAULT_CRON, last)
        except SyncScheduleError:
            return False, 'bad_cron'
        if nxt is not None and now >= nxt:
            return True, 'cron_due'
        return False, 'not_due'

    #: 各項目寫入的 collection 與「有資料」的條件（判斷是不是從來沒真的同步過）
    _JOB_DATA = {
        'translations': ('sc_translations', {'source': 'game'}),
        'items': ('item_master', {'is_current': True}),
        'vehicles': ('vehicle_master', {'is_current': True}),
        'commodities': ('commodity_master', {'is_current': True}),
        'blueprints': ('blueprint_master', {'is_current': True}),
        'factions': ('faction_master', {'is_current': True}),
        'missions': ('mission_master', {'is_current': True}),
        'mining': ('mining_deposit_master', {'is_current': True}),
        'locations': ('starmap_master', {'is_current': True}),
        'uex': ('uex_items', {}),
    }

    @classmethod
    def has_data(cls, key: str) -> bool:
        name, filt = cls._JOB_DATA.get(key, (None, None))
        if not name:
            return True
        return get_db()[name].find_one(filt, {'_id': 1}) is not None

    @classmethod
    def due_jobs(cls, now: datetime = None) -> list:
        """現在到期的項目 [(key, 原因)]，照執行順序。

        ⚠️ 從舊版單一排程升級時，各項目的「上次完成時間」是借舊的最後一輪紀錄
        （避免部署完全部重跑）——但舊版根本沒同步過的新資料庫（任務、勢力）也借到了
        那個時間，結果要等到下一個 cron（最久一週）才第一次同步，期間資料庫是空的。
        所以：還沒被新版真正跑過（沒有 last_run_id）而且資料庫是空的，一律當成
        「從沒跑過」，馬上同步。
        """
        out = []
        for job in cls.all():
            due, reason = cls.is_due(job, now)
            if not due and job.get('enabled', True) and not job.get('last_run_id') \
                    and not cls.has_data(job['key']):
                due, reason = True, 'never_synced'
            if due:
                out.append((job['key'], reason))
        return out

    # ── 執行結果 ───────────────────────────────────────────────

    @classmethod
    def mark_queued(cls, key: str, task_id, at: datetime, by: str = None):
        cls._col().update_one({'_id': key}, {'$set': {
            'queued': True, 'queued_at': at, 'queued_task_id': task_id, 'queued_by': by}}, upsert=True)

    @classmethod
    def clear_queued(cls, key: str, task_id=None):
        """任務結束（或略過）時清掉排隊標記；有給 task_id 就只清自己派的那一筆。"""
        filt = {'_id': key, 'queued': True}
        if task_id:
            filt['queued_task_id'] = task_id
        cls._col().update_one(filt, {'$set': {'queued': False}})

    @staticmethod
    def is_queued(job: dict, now: datetime = None) -> bool:
        if not job.get('queued') or not job.get('queued_at'):
            return False
        now = now or datetime.utcnow()
        return now - job['queued_at'] < timedelta(minutes=QUEUE_STALE_MIN)

    @classmethod
    def mark_started(cls, key: str, run_id: str, at: datetime):
        cls._col().update_one({'_id': key}, {'$set': {
            'running': True, 'running_run_id': run_id, 'running_since': at,
            'queued': False, 'progress': {}, 'progress_at': at}}, upsert=True)

    @classmethod
    def set_progress(cls, key: str, progress: dict):
        """正在跑的這一項目前進度（phase／seen／total），給後台「進行中」區塊即時顯示。"""
        cls._col().update_one({'_id': key}, {'$set': {
            **{f'progress.{k}': v for k, v in (progress or {}).items()},
            'progress_at': datetime.utcnow()}})

    @classmethod
    def record_result(cls, key: str, run_id: str, started: datetime, finished: datetime,
                      ok, error: str = '', stats: dict = None):
        """寫入這一項這次的結果。ok=None 代表略過（例如沒設定 UEX token），不算失敗。"""
        current = cls._col().find_one({'_id': key}, {'consecutive_failures': 1}) or {}
        fails = current.get('consecutive_failures') or 0
        if ok is False:
            fails += 1
        elif ok is True:
            fails = 0
        cls._col().update_one({'_id': key}, {'$set': {
            'running': False,
            'progress': {},
            'last_run_id': run_id,
            'last_started_at': started,
            'last_finished_at': finished,
            'last_duration_s': round((finished - started).total_seconds(), 1),
            'last_ok': ok,
            'last_error': error or None,
            'last_stats': stats or {},
            'consecutive_failures': fails,
        }}, upsert=True)

    @classmethod
    def clear_running(cls):
        """把殘留的 running 標記清掉（worker 被砍掉時不會自己清）。"""
        cls._col().update_many({'running': True}, {'$set': {'running': False}})
