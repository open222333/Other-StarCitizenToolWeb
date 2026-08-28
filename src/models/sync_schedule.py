"""遊戲主檔同步排程設定（DB 版，取代 celeryconfig.py 寫死的 cron）。

單一文件（_id='default'）存在 sync_schedule collection，欄位：
  cron       標準 5 欄位 cron 字串，例如 '30 4 * * 1' = 每週一 04:30
  enabled    是否啟用排程（關掉的話 check_and_run_scheduled_sync 只會略過）
  resources  要同步的資源清單，預設 ['items','vehicles','commodities']
  with_uex   是否連 UEX 一起同步
  updated_at / updated_by

實際觸發邏輯在 tasks/scdata_sync.py 的 check_and_run_scheduled_sync，
由 celeryconfig.py 的 5 分鐘心跳呼叫，每次比對 is_due() 決定要不要真的跑。

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
DEFAULT_RESOURCES = ['items', 'vehicles', 'commodities', 'blueprints']

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
#  排程設定
# ═══════════════════════════════════════════════════════════

class SyncSchedule:
    COLLECTION = 'sync_schedule'

    @classmethod
    def _collection(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def get(cls) -> dict:
        """取得目前排程設定，沒有就建立預設值。"""
        doc = cls._collection().find_one({'_id': _DEFAULT_ID})
        if doc is None:
            doc = {
                '_id': _DEFAULT_ID,
                'cron': DEFAULT_CRON,
                'enabled': True,
                'resources': list(DEFAULT_RESOURCES),
                'with_uex': True,
                'updated_at': datetime.utcnow(),
                'updated_by': None,
            }
            cls._collection().update_one(
                {'_id': _DEFAULT_ID}, {'$setOnInsert': doc}, upsert=True)
            doc = cls._collection().find_one({'_id': _DEFAULT_ID})

        # 前端要顯示「這個 cron 是用哪個時區解讀的」
        doc['timezone'] = str(SCHEDULE_TZ)
        return doc

    @classmethod
    def update(cls, cron=None, enabled=None, resources=None, with_uex=None,
               updated_by=None) -> dict:
        """更新排程設定，cron 會先驗證能不能被解析。"""
        fields: dict = {}

        if cron is not None:
            cron = str(cron).strip()
            if not cls.validate_cron(cron):
                raise SyncScheduleError(f'無效的 cron 表達式：{cron}')
            fields['cron'] = cron

        if enabled is not None:
            fields['enabled'] = bool(enabled)

        if resources is not None:
            if not isinstance(resources, list) or not resources:
                raise SyncScheduleError('resources 必須是非空陣列')
            unknown = [r for r in resources if r not in DEFAULT_RESOURCES]
            if unknown:
                raise SyncScheduleError(
                    f'不支援的資源：{", ".join(map(str, unknown))}')
            fields['resources'] = resources

        if with_uex is not None:
            fields['with_uex'] = bool(with_uex)

        if not fields:
            return cls.get()

        fields['updated_at'] = datetime.utcnow()
        fields['updated_by'] = updated_by

        cls._collection().update_one(
            {'_id': _DEFAULT_ID}, {'$set': fields}, upsert=True)
        return cls.get()

    @staticmethod
    def validate_cron(cron: str) -> bool:
        try:
            parse_cron(cron)
            return True
        except SyncScheduleError:
            return False

    @classmethod
    def next_run(cls, after: datetime = None) -> datetime | None:
        """下一次預計觸發時間（naive UTC）。給後台設定頁顯示用。"""
        schedule = cls.get()
        if not schedule.get('enabled', True):
            return None
        try:
            return next_run_after(schedule.get('cron') or DEFAULT_CRON,
                                  after or datetime.utcnow())
        except SyncScheduleError:
            return None

    @classmethod
    def is_due(cls, last_finished_at, now: datetime = None) -> bool:
        """給定上次同步的完成時間，判斷現在是否該跑下一次。

        沒有任何歷史紀錄（last_finished_at 為 None）視為到期，立刻跑一次。
        """
        schedule = cls.get()
        if not schedule.get('enabled', True):
            return False

        cron = schedule.get('cron') or DEFAULT_CRON
        now = now or datetime.utcnow()

        if last_finished_at is None:
            return True

        try:
            next_run = next_run_after(cron, last_finished_at)
        except SyncScheduleError:
            return False
        return next_run is not None and now >= next_run
