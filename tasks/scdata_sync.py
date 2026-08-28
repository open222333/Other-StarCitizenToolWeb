"""星際公民遊戲資料同步（Celery 任務）。

抓取邏輯在 src/scdata.py，這裡只負責寫入 MongoDB 與批次紀錄。

## 三個關鍵設計

1. **永不刪除。** 每輪同步有一個 run_id；沒被這輪碰到的文件會被標
   is_current=False + retired_at，不會刪掉。舊 patch 移除的物品仍留在 DB，
   這樣 inventory.item_id 的外鍵不會斷。查主檔時記得加 is_current=True。

2. **版本快照。** 每個 patch 額外寫一份 *_versions（_id 是 uuid@version，
   $setOnInsert 只寫一次），用來比對 patch 之間的數值變動。

3. **全域互斥鎖。** 同一時間只允許一輪同步。這不是效能考量而是資料正確性 ——
   見下面「為什麼一定要鎖」。

## 為什麼一定要鎖

`_sync_wiki_resource` 收尾會執行：

    update_many({'_sync.run_id': {'$ne': run_id}}, {'$set': {'is_current': False}})

也就是「不是我這輪寫的，就標成已下架」。如果兩輪同步並行，B 的下架步驟會把
A 剛寫進去的文件全部標成 is_current=False —— 而所有主檔查詢都過濾
is_current=True，結果是物品搜尋、autocomplete、庫存 join 大面積變空，
要等到下一次同步才會恢復。

並行是必然會發生的，不是理論風險：心跳每 5 分鐘跑一次，而全量同步要 5–10
分鐘，紀錄又只在結束時才寫入 sync_runs，所以排程到期時第二次心跳看不到
「正在跑」，就會再開一輪。worker 是 --concurrency=2，兩輪跑得起來。

手動觸發：
    docker compose exec worker python -c \\
      "from tasks.scdata_sync import sync_scdata; print(sync_scdata())"
"""

import logging
import uuid as uuidlib
from contextlib import contextmanager
from datetime import datetime, timedelta

from pymongo import UpdateOne
from redis.exceptions import WatchError

from src import UEX_API_TOKEN
from src.celery_app import celery_app
from src.mongo import get_db
from src.models.sync_schedule import SyncSchedule
from src.redis_client import get_redis
from src.scdata import (BULK_SIZE, UEX_RESOURCES, WIKI_RESOURCES, ScDataError,
                        build_client, uex_doc_id, uex_rows, wiki_rows)

logger = logging.getLogger(__name__)

# ── 互斥鎖 ─────────────────────────────────────────────────────────────
SYNC_LOCK_KEY = 'scdata_sync:lock'
# TTL 遠大於單次同步時間（5–10 分鐘），但仍會過期，
# 這樣 worker 被 kill -9 時鎖不會永遠卡住。
SYNC_LOCK_TTL_S = 3600

# ── 失敗後的重試節奏 ───────────────────────────────────────────────────
# 上游社群 API 常態性不穩，所以失敗不要等到下一個 cron 時段（可能是一週後），
# 但也不能每 5 分鐘就重轟一次 130 個外部請求。
FAILURE_BACKOFF_MIN = 30
# 連續失敗這麼多次就停止 backoff 重試，回到正常 cron 節奏，
# 避免上游長期掛掉時無限重試。
MAX_CONSECUTIVE_FAILURES = 5


def _release_lock(redis, owner: str) -> bool:
    """只在鎖仍是自己持有時才刪掉它。

    「先 GET 再 DELETE」中間鎖可能已過期並被別人取得，那樣就會誤刪別人的鎖。
    用 WATCH/MULTI/EXEC 做 compare-and-delete —— 這是原子操作，
    而且不需要 Lua（fakeredis 預設沒有 EVAL，測試環境也跑得起來）。
    """
    with redis.pipeline() as pipe:
        while True:
            try:
                pipe.watch(SYNC_LOCK_KEY)
                if pipe.get(SYNC_LOCK_KEY) != owner:
                    pipe.unwatch()
                    return False          # 已經不是我的鎖了，不要動
                pipe.multi()
                pipe.delete(SYNC_LOCK_KEY)
                pipe.execute()
                return True
            except WatchError:
                # 期間有人改了這個 key，重新確認一次
                continue


def is_sync_running() -> bool:
    """目前是否有一輪同步正在跑（給 API 層先擋掉重複觸發用）。

    Redis 不可用時回 False —— 寧可讓使用者按得下去，也不要因為
    查不到鎖狀態就永遠不准同步。真正的互斥仍由 sync_lock 保證。
    """
    try:
        return get_redis().exists(SYNC_LOCK_KEY) > 0
    except Exception:
        logger.warning('is_sync_running: Redis 不可用', exc_info=True)
        return False


@contextmanager
def sync_lock(owner: str):
    """全域同步鎖。`with sync_lock(run_id) as acquired:` —— 沒拿到就 acquired=False。

    Redis 不可用時選擇「放行」而不是「擋住」：同步本身比鎖重要，
    而且單一 worker 的情況下並行本來就不會發生。
    """
    try:
        redis = get_redis()
        acquired = bool(redis.set(SYNC_LOCK_KEY, owner, nx=True, ex=SYNC_LOCK_TTL_S))
    except Exception:
        logger.warning('sync_lock: Redis 不可用，這輪不加鎖', exc_info=True)
        yield True
        return

    if not acquired:
        yield False
        return

    try:
        yield True
    finally:
        try:
            _release_lock(redis, owner)
        except Exception:
            # 解鎖失敗不影響同步結果，TTL 會把鎖清掉
            logger.warning('sync_lock: 解鎖失敗，等 TTL 過期', exc_info=True)


def _flush(collection_name: str, ops: list) -> int:
    if not ops:
        return 0
    result = get_db()[collection_name].bulk_write(ops, ordered=False)
    return (result.upserted_count or 0) + (result.modified_count or 0)


def _sync_wiki_resource(client, resource: str, run_id: str, stamp: datetime) -> dict:
    collection_name, mapper = WIKI_RESOURCES[resource]
    history_name = f'{collection_name}_versions'
    db = get_db()

    main_ops: list = []
    history_ops: list = []
    seen = written = skipped = 0

    logger.info('scdata_sync: 同步 %s -> %s', resource, collection_name)

    for row in wiki_rows(client, resource):
        seen += 1
        doc = mapper(row)
        if doc is None:
            skipped += 1
            continue

        doc['_sync'] = {'run_id': run_id, 'at': stamp}
        doc['is_current'] = True

        main_ops.append(UpdateOne(
            {'_id': doc['_id']},
            {'$set': doc, '$setOnInsert': {'first_seen_at': stamp}},
            upsert=True,
        ))

        version = doc.get('game_version')
        if version:
            snapshot = dict(doc)
            snapshot.pop('_sync', None)
            snapshot.pop('is_current', None)
            # raw 是完整的 API 原始 JSON，主檔已經有一份了。
            # 版本快照每個 patch 都會多存一份，帶著 raw 會讓 *_versions
            # 長成 item_master 的 10–20 倍體積，而比對數值變動只需要拉平後的欄位。
            snapshot.pop('raw', None)
            snapshot['item_uuid'] = doc['_id']
            snapshot['_id'] = f"{doc['_id']}@{version}"
            history_ops.append(UpdateOne(
                {'_id': snapshot['_id']},
                {'$setOnInsert': {**snapshot, 'snapshot_at': stamp}},
                upsert=True,
            ))

        if len(main_ops) >= BULK_SIZE:
            written += _flush(collection_name, main_ops)
            _flush(history_name, history_ops)
            main_ops, history_ops = [], []

    written += _flush(collection_name, main_ops)
    _flush(history_name, history_ops)

    # ⚠️ 上游回空清單時**不要**下架 —— 否則一次失敗的抓取就會把整個主檔
    #    標成已下架，所有查詢（都過濾 is_current=True）瞬間變空。
    #    這種情況當成錯誤往上拋，讓這輪記成失敗並走 backoff 重試。
    if seen == 0:
        raise ScDataError(
            f'{resource}: 上游回傳 0 筆資料，跳過下架步驟以免清空主檔')

    # 這輪沒碰到的 → 目前 patch 已不存在，但保留紀錄
    retired = db[collection_name].update_many(
        {'_sync.run_id': {'$ne': run_id}, 'is_current': {'$ne': False}},
        {'$set': {'is_current': False, 'retired_at': stamp}},
    ).modified_count

    logger.info('scdata_sync: %s 完成 讀取=%d 寫入=%d 跳過=%d 下架=%d',
                resource, seen, written, skipped, retired)
    return {'resource': resource, 'collection': collection_name, 'seen': seen,
            'written': written, 'skipped': skipped, 'retired': retired}


def _sync_uex_resource(client, resource: str, run_id: str, stamp: datetime) -> dict:
    collection_name, key_fields = UEX_RESOURCES[resource]
    logger.info('scdata_sync: 同步 UEX %s -> %s', resource, collection_name)

    rows = uex_rows(client, resource)
    ops: list = []
    skipped = 0

    for row in rows:
        doc_id = uex_doc_id(row, key_fields)
        if doc_id is None:
            skipped += 1
            continue

        doc = dict(row)
        doc['_id'] = doc_id
        # UEX items 的 uuid 對應 item_master._id；沒有就留 None
        doc['wiki_uuid'] = row.get('uuid') or None
        doc['_sync'] = {'run_id': run_id, 'at': stamp}
        ops.append(UpdateOne(
            {'_id': doc_id},
            {'$set': doc, '$setOnInsert': {'first_seen_at': stamp}},
            upsert=True,
        ))

        if len(ops) >= BULK_SIZE:
            _flush(collection_name, ops)
            ops = []

    _flush(collection_name, ops)
    logger.info('scdata_sync: UEX %s 完成 %d 筆（跳過 %d）', resource, len(rows), skipped)
    return {'resource': f'uex:{resource}', 'collection': collection_name,
            'seen': len(rows), 'written': len(rows) - skipped, 'skipped': skipped}


def _do_sync(resources=None, with_uex: bool = True) -> dict:
    """同步的核心邏輯，寫入 sync_runs 並回傳摘要。

    刻意是純函式而不是 Celery task —— 這樣 `sync_scdata`（走 Celery 的
    retry 語意）與 `check_and_run_scheduled_sync`（自己管 backoff）可以
    共用同一份邏輯。

    上游整體不可用時往上拋 ScDataError，由呼叫端決定重試策略。
    """
    resources = list(resources or WIKI_RESOURCES.keys())
    unknown = [r for r in resources if r not in WIKI_RESOURCES]
    if unknown:
        raise ValueError(f'未知的資源: {", ".join(unknown)}')

    run_id = str(uuidlib.uuid4())
    started = datetime.utcnow()
    stats: list = []
    errors: list = []

    logger.info('scdata_sync: 開始 run_id=%s resources=%s', run_id, resources)

    with build_client() as client:
        for resource in resources:
            try:
                stats.append(_sync_wiki_resource(client, resource, run_id, started))
            except Exception as err:
                # 一個資源失敗不要拖垮其他的
                logger.exception('scdata_sync: %s 失敗', resource)
                errors.append(f'{resource}: {err}')

    if with_uex:
        if not UEX_API_TOKEN:
            logger.warning('scdata_sync: 沒有 UEX_API_TOKEN，跳過 UEX 同步。'
                           '到 https://uexcorp.space/api/apps 建 app 取得免費 token')
        else:
            with build_client(token=UEX_API_TOKEN) as uex_client:
                for resource in UEX_RESOURCES:
                    try:
                        stats.append(
                            _sync_uex_resource(uex_client, resource, run_id, started))
                    except Exception as err:
                        logger.exception('scdata_sync: UEX %s 失敗', resource)
                        errors.append(f'uex:{resource}: {err}')

    finished = datetime.utcnow()
    summary = {
        '_id': run_id,
        'started_at': started,
        'finished_at': finished,
        'duration_s': round((finished - started).total_seconds(), 1),
        'resources': resources,
        'with_uex': with_uex and bool(UEX_API_TOKEN),
        'stats': stats,
        'errors': errors,
        'ok': not errors,
    }
    get_db()['sync_runs'].insert_one(summary)

    logger.info('scdata_sync: 結束 %.1fs errors=%d', summary['duration_s'], len(errors))
    return {'run_id': run_id, 'duration_s': summary['duration_s'],
            'ok': summary['ok'], 'errors': errors,
            'stats': [{k: s[k] for k in ('resource', 'seen', 'written', 'retired')
                       if k in s} for s in stats]}


@celery_app.task(name='tasks.scdata_sync.sync_scdata', bind=True, max_retries=2)
def sync_scdata(self, resources=None, with_uex: bool = True):
    """同步遊戲主檔（手動觸發用，例如後台的「立即同步」按鈕）。

    :param resources: 要同步的資源清單，預設全部（items / vehicles / commodities）
    :param with_uex: 是否同步 UEX 價格（沒有 UEX_API_TOKEN 會自動跳過）
    """
    run_id = str(uuidlib.uuid4())
    with sync_lock(run_id) as acquired:
        if not acquired:
            logger.info('sync_scdata: 已有另一輪同步進行中，略過')
            return {'skipped': True, 'reason': 'already_running'}

        try:
            return _do_sync(resources=resources, with_uex=with_uex)
        except ScDataError as exc:
            # 上游整體不可用 → 退避重試，不要寫一筆假的成功紀錄。
            # 注意：這條路徑只在透過 .delay() 派送時有效
            #（Task.retry 在 called_directly 時會直接重拋原例外），
            # 所以心跳那支不走這裡，見 check_and_run_scheduled_sync。
            logger.error('scdata_sync: 上游 API 不可用: %s', exc)
            raise self.retry(exc=exc, countdown=600)


def _consecutive_failures(limit: int = MAX_CONSECUTIVE_FAILURES + 1) -> int:
    """從最新往回數，連續有幾次同步是失敗的。"""
    # 用 started_at 排序（src/mongo.py 的索引建在這個欄位上）。
    # 同步是互斥的，所以 started_at 的先後等於 finished_at 的先後。
    runs = get_db()['sync_runs'].find(
        {}, {'ok': 1}, sort=[('started_at', -1)], limit=limit)
    count = 0
    for run in runs:
        if run.get('ok'):
            break
        count += 1
    return count


def _is_due() -> tuple:
    """判斷現在該不該同步，回傳 (是否到期, 原因)。"""
    schedule = SyncSchedule.get()
    if not schedule.get('enabled', True):
        return False, 'disabled'

    # ⚠️ 基準是「最後一次**嘗試**」而不是「最後一次成功」。
    #    只看成功紀錄的話，一旦上游有任何部分失敗（errors 非空 → ok=False），
    #    這輪就完全不算，5 分鐘後又會判定到期，變成無限重跑全量同步。
    last = get_db()['sync_runs'].find_one({}, sort=[('started_at', -1)])
    if not last:
        return True, 'never_run'

    last_finished = last.get('finished_at')
    now = datetime.utcnow()

    if not last.get('ok'):
        fails = _consecutive_failures()
        if fails < MAX_CONSECUTIVE_FAILURES:
            # 失敗後走較短的 backoff，不必等到下一個 cron 時段
            if last_finished and now >= last_finished + timedelta(minutes=FAILURE_BACKOFF_MIN):
                return True, f'retry_after_failure({fails})'
            return False, f'failure_backoff({fails})'
        # 連續失敗太多次 → 上游可能長期掛掉，回到正常 cron 節奏
        logger.warning('_is_due: 已連續失敗 %d 次，回到 cron 節奏', fails)

    if SyncSchedule.is_due(last_finished, now=now):
        return True, 'cron_due'
    return False, 'not_due'


@celery_app.task(name='tasks.scdata_sync.check_and_run_scheduled_sync')
def check_and_run_scheduled_sync():
    """每 5 分鐘的心跳（見 tasks/celeryconfig.py 的 check-sync-schedule）。

    排程本身存在 DB（src/models/sync_schedule.py），可在後台「設定」頁面編輯，
    不用改 celeryconfig.py、也不用重啟 worker/beat。這支只是：

      1. 讀排程設定，enabled=False 就什麼都不做
      2. 依「最後一次嘗試」判斷是否到期（失敗會走較短的 backoff）
      3. 搶全域鎖 —— 搶不到表示另一輪還在跑，直接略過
      4. 呼叫 _do_sync()（不是 .delay()，也不是 sync_scdata()，
         因為 Celery 的 Task.retry 在直接呼叫時不會排重試，
         這裡的重試節奏由第 2 步的 backoff 負責）
    """
    due, reason = _is_due()
    if not due:
        logger.debug('check_and_run_scheduled_sync: 略過（%s）', reason)
        return {'skipped': True, 'reason': reason}

    run_id = str(uuidlib.uuid4())
    with sync_lock(run_id) as acquired:
        if not acquired:
            # 上一輪還在跑（全量同步要 5–10 分鐘，心跳每 5 分鐘一次，
            # 所以這是正常情況，不是錯誤）
            logger.info('check_and_run_scheduled_sync: 已有同步進行中，略過')
            return {'skipped': True, 'reason': 'already_running'}

        schedule = SyncSchedule.get()
        logger.info('check_and_run_scheduled_sync: 開始同步（%s）cron=%s',
                    reason, schedule.get('cron'))
        try:
            result = _do_sync(
                resources=schedule.get('resources') or None,
                with_uex=schedule.get('with_uex', True),
            )
        except ScDataError as exc:
            # 上游整體不可用。不用 self.retry（直接呼叫時無效），
            # 改成寫一筆失敗紀錄讓 _is_due 的 backoff 接手。
            logger.error('check_and_run_scheduled_sync: 上游 API 不可用: %s', exc)
            now = datetime.utcnow()
            get_db()['sync_runs'].insert_one({
                '_id': run_id,
                'started_at': now,
                'finished_at': now,
                'duration_s': 0,
                'resources': schedule.get('resources') or list(WIKI_RESOURCES.keys()),
                'with_uex': schedule.get('with_uex', True),
                'stats': [],
                'errors': [f'上游 API 不可用: {exc}'],
                'ok': False,
            })
            return {'skipped': False, 'ok': False, 'error': str(exc)}

        return {'skipped': False, 'result': result}
