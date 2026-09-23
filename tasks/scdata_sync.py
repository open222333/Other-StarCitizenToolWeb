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
from src import SCDATA_TRANSLATION_INI_URL
from src.models import translation as translation_model
from src.scdata import (BULK_SIZE, SCUNPACKED_LABELS_PATH, SCUNPACKED_RESOURCES, UEX_RESOURCES,
                        WIKI_RESOURCES, ScDataError, build_client, fetch_scunpacked_rows,
                        fetch_translation_ini, iter_translation_entries, normalize_labels,
                        uex_doc_id,
                        uex_rows, wiki_rows)

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

    # ⚠️ 上游資料「短少」時**不要**下架 —— 否則一次不完整的抓取就會把主檔
    #    大半標成已下架，所有查詢（都過濾 is_current=True）瞬間變空。
    #
    #    原本只擋 seen == 0，但真正會發生的情況比那個更陰險：Wiki API 是
    #    跟著 links.next 走分頁的，只要某次回應少了 links.next（上游出錯、
    #    中間有快取代理、或剛好 deploy），迴圈就會提早結束 —— seen=100
    #    而實際有 20,000 筆，然後把其餘 19,900 筆全部下架，這輪還記成成功。
    #    症狀是物品搜尋、bot autocomplete、庫存名稱 join 全部變空，
    #    而且要等下一次成功的完整同步才會恢復。
    #
    #    所以改成跟「上次同步後還在架上的筆數」比：少於 80% 就當成抓取不完整
    #    往上拋，讓這輪記成失敗並走 backoff 重試，主檔維持原狀。
    #    首次同步（before == 0）沒有基準，只要有資料就放行。
    before_current = db[collection_name].count_documents({'is_current': {'$ne': False}})
    floor = int(before_current * 0.8)
    if seen == 0 or (before_current and seen < floor):
        raise ScDataError(
            f'{resource}: 上游只回傳 {seen} 筆，低於原有上架筆數 {before_current} 的 80%'
            f'（門檻 {floor}），判定抓取不完整，跳過下架步驟以免清空主檔')

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


def _sync_scunpacked_resource(client, resource: str, run_id: str, stamp: datetime) -> dict:
    """同步 scunpacked-data 的靜態礦物回波參考表。

    跟 _sync_wiki_resource 不同：來源沒有分頁，一次 GET 一個 JSON 檔就是全部，
    所以「讀取筆數 seen」在這裡是「檔案裡的項目數」而不是「累積跨頁筆數」。
    is_current / retired_at / 80% 下架門檻的保護邏輯照抄 _sync_wiki_resource，
    理由一樣：上游檔案任何一次抓取異常變短，都不該把既有參考表下架清空。
    """
    collection_name, path, mapper = SCUNPACKED_RESOURCES[resource]
    db = get_db()

    logger.info('scdata_sync: 同步 scunpacked %s -> %s', resource, collection_name)

    rows = fetch_scunpacked_rows(client, path)
    ops: list = []
    seen = written = skipped = 0

    for row in rows:
        seen += 1
        doc = mapper(row)
        if doc is None:
            skipped += 1
            continue

        doc['_sync'] = {'run_id': run_id, 'at': stamp}
        doc['is_current'] = True

        ops.append(UpdateOne(
            {'_id': doc['_id']},
            {'$set': doc, '$setOnInsert': {'first_seen_at': stamp}},
            upsert=True,
        ))

        if len(ops) >= BULK_SIZE:
            written += _flush(collection_name, ops)
            ops = []

    written += _flush(collection_name, ops)

    before_current = db[collection_name].count_documents({'is_current': {'$ne': False}})
    floor = int(before_current * 0.8)
    if seen == 0 or (before_current and seen < floor):
        raise ScDataError(
            f'scunpacked:{resource}: 上游只回傳 {seen} 筆，低於原有上架筆數 {before_current} 的 80%'
            f'（門檻 {floor}），判定抓取不完整，跳過下架步驟以免清空主檔')

    retired = db[collection_name].update_many(
        {'_sync.run_id': {'$ne': run_id}, 'is_current': {'$ne': False}},
        {'$set': {'is_current': False, 'retired_at': stamp}},
    ).modified_count

    logger.info('scdata_sync: scunpacked %s 完成 讀取=%d 寫入=%d 跳過=%d 下架=%d',
                resource, seen, written, skipped, retired)
    return {'resource': f'scunpacked:{resource}', 'collection': collection_name, 'seen': seen,
            'written': written, 'skipped': skipped, 'retired': retired}


TRANSLATION_LANG = 'zh-TW'


def _sync_translations(client, run_id: str, stamp: datetime) -> dict:
    """同步遊戲文字翻譯到 sc_translations（全站中文化的唯一來源）。

    英文（主語言）來自 scunpacked-data 的 labels.json，繁中來自社群翻譯包的
    global.ini，兩邊 key 一樣，一個 key 一筆；翻譯包沒有的人工條目
    （src/data/sc_translation_manual.json）一併寫入。見 src/models/translation.py。

    跑在其他資源之前：物品／礦物的 name_zh 是同步當下查表寫進主檔的，
    同一輪同步就要用到這次更新的翻譯。

    保護：翻譯包或英文表任何一份下載異常變短（< 原有筆數 80%）就整個跳過，
    不要讓「下載到半份檔案」把九成翻譯刪掉。
    """
    logger.info('scdata_sync: 同步翻譯（英文表 + %s）', TRANSLATION_LANG)
    manual = translation_model.sync_manual(stamp)

    before = translation_model.count(translation_model.SOURCE_GAME)
    floor = int(before * 0.8)

    # 英文表先轉成精簡的 {key: 英文} 就丟掉原始 dict，再下載翻譯包（記憶體考量，
    # 見 normalize_labels）
    english = normalize_labels(fetch_scunpacked_rows(client, SCUNPACKED_LABELS_PATH, expect=dict))
    if len(english) < max(1000, floor):
        raise ScDataError(f'translations: 英文表只有 {len(english)} 筆，低於原有 {before} 筆的 80%，跳過')
    ini_text = fetch_translation_ini(client)
    ini_lines = ini_text.count('\n')
    if ini_lines < max(1000, floor):
        raise ScDataError(f'translations: 翻譯包只有 {ini_lines} 行，低於原有 {before} 筆的 80%，跳過')

    stats = translation_model.replace_source(
        iter_translation_entries(english, ini_text, TRANSLATION_LANG),
        translation_model.SOURCE_GAME, stamp)
    del english, ini_text

    translation_model.mark_synced(
        run_id, stamp,
        langs=[translation_model.LANG_EN, TRANSLATION_LANG],
        sources={translation_model.LANG_EN: f'scunpacked-data/{SCUNPACKED_LABELS_PATH}',
                 TRANSLATION_LANG: SCDATA_TRANSLATION_INI_URL},
        counts={'game': stats['seen'], 'manual': manual['seen']})

    logger.info('scdata_sync: 翻譯完成 條目=%d 寫入=%d 移除=%d 人工=%d',
                stats['seen'], stats['written'], stats['retired'], manual['seen'])
    return {'resource': 'translations', 'collection': translation_model.COLLECTION,
            'seen': stats['seen'], 'written': stats['written'],
            'retired': stats['retired'], 'manual': manual['seen']}


def _do_sync(resources=None, with_uex: bool = True, with_scunpacked: bool = True,
             with_translations: bool = True, translations_only: bool = False) -> dict:
    """同步的核心邏輯，寫入 sync_runs 並回傳摘要。

    刻意是純函式而不是 Celery task —— 這樣 `sync_scdata`（走 Celery 的
    retry 語意）與 `check_and_run_scheduled_sync`（自己管 backoff）可以
    共用同一份邏輯。

    上游整體不可用時往上拋 ScDataError，由呼叫端決定重試策略。

    translations_only：只同步翻譯（部署後資料庫還沒有翻譯時，心跳會自動跑一次，
    見 check_and_run_scheduled_sync）。
    """
    resources = [] if translations_only else list(resources or WIKI_RESOURCES.keys())
    if translations_only:
        with_uex = with_scunpacked = False
        with_translations = True
    unknown = [r for r in resources if r not in WIKI_RESOURCES]
    if unknown:
        raise ValueError(f'未知的資源: {", ".join(unknown)}')

    run_id = str(uuidlib.uuid4())
    started = datetime.utcnow()
    stats: list = []
    errors: list = []

    logger.info('scdata_sync: 開始 run_id=%s resources=%s', run_id, resources)

    if with_translations:
        with build_client() as tr_client:
            try:
                stats.append(_sync_translations(tr_client, run_id, started))
            except Exception as err:
                # 翻譯失敗不影響主檔同步——主檔照樣用資料庫裡上一版的翻譯
                logger.exception('scdata_sync: 翻譯同步失敗')
                errors.append(f'translations: {err}')

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

    # scunpacked-data 是公開靜態檔案，不用 token、沒有速率限制，跟 with_uex
    # 不同的是沒有「沒設定就跳過」這回事——預設一律開啟。
    if with_scunpacked:
        with build_client() as scunpacked_client:
            for resource in SCUNPACKED_RESOURCES:
                try:
                    stats.append(
                        _sync_scunpacked_resource(scunpacked_client, resource, run_id, started))
                except Exception as err:
                    logger.exception('scdata_sync: scunpacked %s 失敗', resource)
                    errors.append(f'scunpacked:{resource}: {err}')

    finished = datetime.utcnow()
    summary = {
        '_id': run_id,
        'started_at': started,
        'finished_at': finished,
        'duration_s': round((finished - started).total_seconds(), 1),
        'resources': resources,
        'with_uex': with_uex and bool(UEX_API_TOKEN),
        'with_scunpacked': with_scunpacked,
        'with_translations': with_translations,
        'translations_only': translations_only,
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
def sync_scdata(self, resources=None, with_uex: bool = True, with_scunpacked: bool = True,
                with_translations: bool = True):
    """同步遊戲主檔（手動觸發用，例如後台的「立即同步」按鈕）。

    :param resources: 要同步的資源清單，預設全部（items / vehicles / commodities / blueprints）
    :param with_uex: 是否同步 UEX 價格（沒有 UEX_API_TOKEN 會自動跳過）
    :param with_scunpacked: 是否同步礦物回波參考表（scunpacked-data，預設開啟）
    :param with_translations: 是否同步遊戲文字翻譯（英文表＋社群繁中化包，預設開啟）
    """
    run_id = str(uuidlib.uuid4())
    with sync_lock(run_id) as acquired:
        if not acquired:
            logger.info('sync_scdata: 已有另一輪同步進行中，略過')
            return {'skipped': True, 'reason': 'already_running'}

        try:
            return _do_sync(resources=resources, with_uex=with_uex,
                            with_scunpacked=with_scunpacked,
                            with_translations=with_translations)
        except ScDataError as exc:
            # 上游整體不可用 → 退避重試，不要寫一筆假的成功紀錄。
            # 注意：這條路徑只在透過 .delay() 派送時有效
            #（Task.retry 在 called_directly 時會直接重拋原例外），
            # 所以心跳那支不走這裡，見 check_and_run_scheduled_sync。
            logger.error('scdata_sync: 上游 API 不可用: %s', exc)
            raise self.retry(exc=exc, countdown=600)


#: 排程到期／失敗 backoff 只看一般同步的紀錄：部署後自動補跑的「只同步翻譯」
#: 不該把下一次全量同步往後推，也不該被當成全量同步失敗
_SCHEDULED_RUNS = {'translations_only': {'$ne': True}}


def _consecutive_failures(limit: int = MAX_CONSECUTIVE_FAILURES + 1) -> int:
    """從最新往回數，連續有幾次同步是失敗的。"""
    # 用 started_at 排序（src/mongo.py 的索引建在這個欄位上）。
    # 同步是互斥的，所以 started_at 的先後等於 finished_at 的先後。
    runs = get_db()['sync_runs'].find(
        _SCHEDULED_RUNS, {'ok': 1}, sort=[('started_at', -1)], limit=limit)
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
    last = get_db()['sync_runs'].find_one(_SCHEDULED_RUNS, sort=[('started_at', -1)])
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


TRANSLATION_BOOTSTRAP_RETRY = timedelta(minutes=30)


def _translations_bootstrap():
    """資料庫沒有翻譯時先只同步翻譯；有翻譯（或 30 分鐘內剛試過）回 None。"""
    status = translation_model.status()
    if status.get('version'):
        return None
    last = status.get('bootstrap_attempt_at')
    now = datetime.utcnow()
    if last and now - last < TRANSLATION_BOOTSTRAP_RETRY:
        return None

    run_id = str(uuidlib.uuid4())
    with sync_lock(run_id) as acquired:
        if not acquired:
            return None
        get_db()[translation_model.META_COLLECTION].update_one(
            {'_id': 'status'}, {'$set': {'bootstrap_attempt_at': now}}, upsert=True)
        logger.info('check_and_run_scheduled_sync: 資料庫沒有翻譯，先同步翻譯')
        try:
            return _do_sync(translations_only=True)
        except ScDataError as exc:
            logger.error('check_and_run_scheduled_sync: 翻譯同步失敗: %s', exc)
            return {'ok': False, 'errors': [str(exc)]}


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
    # 資料庫還沒有任何翻譯（剛部署、或 sc_translations 被清掉）時，不等排程到期，
    # 先只同步翻譯——否則全站中文化要等下一次排程（預設一週）才會出現。
    # 失敗的話 30 分鐘後才再試，不要每 5 分鐘打一次 GitHub。
    bootstrap = _translations_bootstrap()
    if bootstrap is not None:
        return bootstrap

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
                # SyncSchedule 目前沒有 with_scunpacked 欄位（見 src/models/sync_schedule.py）
                # ——礦物回波參考表資料量小、無 token 限制，先預設一律跟著心跳同步，
                # 之後真的要讓後台可關閉再補欄位。
                with_scunpacked=schedule.get('with_scunpacked', True),
                with_translations=schedule.get('with_translations', True),
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
