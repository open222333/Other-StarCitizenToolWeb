"""星際公民遊戲資料同步（Celery 任務）。

抓取邏輯在 src/scdata.py，這裡只負責寫入 MongoDB 與批次紀錄。

## 三個關鍵設計

1. **永不刪除。** 每輪同步有一個 run_id；沒被這輪碰到的文件會被標
   is_current=False + retired_at，不會刪掉。舊 patch 移除的物品仍留在 DB，
   這樣 inventory.item_id 的外鍵不會斷。查主檔時記得加 is_current=True。

2. **版本快照。** 每個 patch 額外寫一份 *_versions（_id 是 uuid@version，
   $setOnInsert 只寫一次），用來比對 patch 之間的數值變動。

3. **每個同步項目一把鎖。** 同一個項目（同一個 collection）同一時間只允許一輪，
   不同項目可以同時跑（各自一個 Celery 任務）。這不是效能考量而是資料正確性 ——
   見下面「為什麼一定要鎖」。

## 為什麼一定要鎖

`_sync_wiki_resource` 收尾會執行：

    update_many({'_sync.run_id': {'$ne': run_id}}, {'$set': {'is_current': False}})

也就是「不是我這輪寫的，就標成已下架」。如果兩輪同步並行，B 的下架步驟會把
A 剛寫進去的文件全部標成 is_current=False —— 而所有主檔查詢都過濾
is_current=True，結果是物品搜尋、autocomplete、庫存 join 大面積變空，
要等到下一次同步才會恢復。

並行是必然會發生的，不是理論風險：心跳每 5 分鐘跑一次，而物品同步要好幾分鐘，
手動同步也可能剛好撞上排程。下架步驟只影響同一個 collection，所以鎖是「每個
同步項目一把」（`scdata_sync:lock:<項目>`）：同一項不會並行，不同項目可以同時跑。
翻譯同步跟其他項目並行也安全——replace_source 是逐筆 upsert、最後才刪掉舊 key，
其他項目查中文時看到的不是舊值就是新值。

手動觸發（全部，或指定項目，例如只同步任務）：
    docker compose exec worker python -c \\
      "from tasks.scdata_sync import sync_scdata; print(sync_scdata(jobs=['missions']))"
"""

import logging
import time
import uuid as uuidlib
from contextlib import contextmanager
from datetime import datetime, timedelta

from pymongo import UpdateOne
from redis.exceptions import WatchError

from src.models.app_setting import UexToken
from src.celery_app import celery_app
from src.mongo import get_db
from src.models.sync_schedule import (FAILURE_BACKOFF_MIN, JOB_KEYS,  # noqa: F401（測試沿用）
                                      MAX_CONSECUTIVE_FAILURES, SyncJobs, order_jobs)
from src.redis_client import get_redis
from src import SCDATA_TRANSLATION_INI_URL
from src.models import translation as translation_model
from src.models.mission import Faction, Mission
from src.models import visibility
from src.models.item import VehicleMaster
from src.models.starmap import Starmap
from src import SCDATA_REQUEST_DELAY
from src.scdata import (BULK_SIZE, SCUNPACKED_JOBS, SCUNPACKED_LABELS_PATH, SCUNPACKED_RESOURCES,
                        UEX_RESOURCES,
                        WIKI_DETAIL_RESOURCES, WIKI_RESOURCES, ScDataError, build_client,
                        fetch_scunpacked_rows, fetch_translation_ini, iter_translation_entries,
                        normalize_labels, uex_doc_id, uex_rows, wiki_detail, wiki_rows)

logger = logging.getLogger(__name__)

# ── 互斥鎖 ─────────────────────────────────────────────────────────────
SYNC_LOCK_KEY = 'scdata_sync:lock'
# TTL 遠大於單次同步時間（5–10 分鐘），但仍會過期，
# 這樣 worker 被 kill -9 時鎖不會永遠卡住。
SYNC_LOCK_TTL_S = 3600

# 失敗後的重試節奏（FAILURE_BACKOFF_MIN／MAX_CONSECUTIVE_FAILURES）在
# src/models/sync_schedule.py，每個同步項目各自計算。


def job_lock_key(job: str) -> str:
    """某個同步項目的鎖（不同項目可以同時同步，同一項不行）。"""
    return f'{SYNC_LOCK_KEY}:{job}'


def _release_lock(redis, owner: str, key: str = SYNC_LOCK_KEY) -> bool:
    """只在鎖仍是自己持有時才刪掉它。

    「先 GET 再 DELETE」中間鎖可能已過期並被別人取得，那樣就會誤刪別人的鎖。
    用 WATCH/MULTI/EXEC 做 compare-and-delete —— 這是原子操作，
    而且不需要 Lua（fakeredis 預設沒有 EVAL，測試環境也跑得起來）。
    """
    with redis.pipeline() as pipe:
        while True:
            try:
                pipe.watch(key)
                if pipe.get(key) != owner:
                    pipe.unwatch()
                    return False          # 已經不是我的鎖了，不要動
                pipe.multi()
                pipe.delete(key)
                pipe.execute()
                return True
            except WatchError:
                # 期間有人改了這個 key，重新確認一次
                continue


def running_jobs() -> list:
    """目前正在同步的項目（看各項目的鎖，照 SYNC_JOBS 順序）。

    Redis 不可用時回空清單 —— 寧可讓使用者按得下去，也不要因為
    查不到鎖狀態就永遠不准同步。真正的互斥仍由 sync_lock 保證。
    """
    try:
        redis = get_redis()
        pipe = redis.pipeline()
        for key in JOB_KEYS:
            pipe.exists(job_lock_key(key))
        return [k for k, held in zip(JOB_KEYS, pipe.execute()) if held]
    except Exception:
        logger.warning('running_jobs: Redis 不可用', exc_info=True)
        return []


def is_sync_running() -> bool:
    """目前是否有任何同步正在跑。"""
    try:
        if get_redis().exists(SYNC_LOCK_KEY) > 0:
            return True
    except Exception:
        logger.warning('is_sync_running: Redis 不可用', exc_info=True)
        return False
    return bool(running_jobs())


@contextmanager
def sync_lock(owner: str, key: str = SYNC_LOCK_KEY):
    """同步鎖。`with sync_lock(run_id, job_lock_key('items')) as acquired:` —— 沒拿到就
    acquired=False。key 預設是舊的全域鎖（只剩測試與相容用途）。

    Redis 不可用時選擇「放行」而不是「擋住」：同步本身比鎖重要，
    而且單一 worker 的情況下並行本來就不會發生。
    """
    try:
        redis = get_redis()
        acquired = bool(redis.set(key, owner, nx=True, ex=SYNC_LOCK_TTL_S))
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
            _release_lock(redis, owner, key)
        except Exception:
            # 解鎖失敗不影響同步結果，TTL 會把鎖清掉
            logger.warning('sync_lock: 解鎖失敗，等 TTL 過期', exc_info=True)


# ── 進度回報（後台「資料同步排程」頁的「進行中」區塊）─────────────────
# 每個 worker process 一次只跑一個任務，所以「目前在跑哪一項」放模組變數就夠了。
# 寫入有節流（最多每 2 秒一次），不要每一筆都打 Mongo。
_progress_job = None
_progress_last = 0.0
PROGRESS_INTERVAL_S = 2.0


def _report(force: bool = False, **fields):
    global _progress_last
    if not _progress_job:
        return
    now = time.monotonic()
    if not force and now - _progress_last < PROGRESS_INTERVAL_S:
        return
    _progress_last = now
    try:
        SyncJobs.set_progress(_progress_job, fields)
    except Exception:
        logger.debug('scdata_sync: 寫入進度失敗', exc_info=True)


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

    with_detail = resource in WIKI_DETAIL_RESOURCES
    expected = db[collection_name].count_documents({'is_current': {'$ne': False}})
    _report(force=True, phase='讀取 Star Citizen Wiki API', seen=0, total=expected or None)

    for row in wiki_rows(client, resource):
        seen += 1
        _report(seen=seen, total=expected or None)
        if with_detail and row.get('uuid'):
            # 列表欄位不夠的資源（見 src/scdata.py 的 WIKI_DETAIL_RESOURCES）逐筆補明細，
            # 抓失敗就用列表那筆
            detail = wiki_detail(client, resource, row['uuid'])
            if detail:
                row = {**row, **detail}
            time.sleep(SCDATA_REQUEST_DELAY)
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
    _report(force=True, phase='下架已移除的項目', seen=seen, total=expected or None)

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
    _report(force=True, phase=f'下載 UEX {resource}')

    rows = uex_rows(client, resource)
    _report(force=True, phase=f'寫入 UEX {resource}', seen=0, total=len(rows))
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

    _report(force=True, phase=f'下載 {path}')
    rows = fetch_scunpacked_rows(client, path)
    ops: list = []
    seen = written = skipped = 0
    _report(force=True, phase=f'寫入 {resource}', seen=0, total=len(rows))

    for row in rows:
        seen += 1
        _report(seen=seen, total=len(rows))
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
    _report(force=True, phase='下載英文表（labels.json）')
    english = normalize_labels(fetch_scunpacked_rows(client, SCUNPACKED_LABELS_PATH, expect=dict))
    if len(english) < max(1000, floor):
        raise ScDataError(f'translations: 英文表只有 {len(english)} 筆，低於原有 {before} 筆的 80%，跳過')
    _report(force=True, phase='下載社群翻譯包（global.ini）')
    ini_text = fetch_translation_ini(client)
    ini_lines = ini_text.count('\n')
    if ini_lines < max(1000, floor):
        raise ScDataError(f'translations: 翻譯包只有 {ini_lines} 行，低於原有 {before} 筆的 80%，跳過')

    _report(force=True, phase='寫入翻譯資料庫')
    stats = translation_model.replace_source(
        iter_translation_entries(english, ini_text, TRANSLATION_LANG),
        translation_model.SOURCE_GAME, stamp)
    del english, ini_text
    # 舊條目沒有 en_norm（寬鬆比對用），內容沒變的同步時不會重寫，這裡補上
    translation_model.backfill_en_norm()

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


def _run_job(key: str, run_id: str, stamp: datetime, clients: dict) -> tuple:
    """跑單一同步項目，回傳 (stats 清單, 錯誤清單, ok)。ok=None 代表略過（不算失敗）。

    clients 是這一輪共用的 httpx client（同一種來源只建一次），呼叫端負責關閉。
    """
    def client(name, **kw):
        if name not in clients:
            clients[name] = build_client(**kw)
        return clients[name]

    stats, errors = [], []

    if key == 'translations':
        try:
            stats.append(_sync_translations(client('github'), run_id, stamp))
        except Exception as err:
            # 翻譯失敗不影響主檔同步——主檔照樣用資料庫裡上一版的翻譯
            logger.exception('scdata_sync: 翻譯同步失敗')
            errors.append(f'translations: {err}')
        if not errors:
            # 任務／勢力的中文是同步當下的快照；翻譯更新後重新比對一次，
            # 不用等任務、勢力下次同步（兩者也可能剛好同時在跑）
            try:
                _report(force=True, phase='重新比對任務、勢力、地點的中文')
                logger.info('scdata_sync: 任務中文更新 %d 筆、勢力 %d 筆、地點 %d 筆',
                            Mission.refresh_translations(), Faction.refresh_translations(),
                            Starmap.refresh_translations())
            except Exception:
                logger.exception('scdata_sync: 重新比對任務、勢力中文失敗')

    elif key in WIKI_RESOURCES:
        try:
            stats.append(_sync_wiki_resource(client('wiki'), key, run_id, stamp))
        except Exception as err:
            logger.exception('scdata_sync: %s 失敗', key)
            errors.append(f'{key}: {err}')
        if key == 'blueprints' and not errors:
            # 任務的獎勵藍圖有些要靠藍圖主檔反查（見 src/scdata.py 的 parse_blueprint_pools），
            # 藍圖更新後重新對一次，任務跟藍圖誰先同步都沒關係
            try:
                _report(force=True, phase='重新對應任務的獎勵藍圖')
                relinked = Mission.relink_blueprints()
                logger.info('scdata_sync: 重新對應任務獎勵藍圖 %d 筆', relinked)
            except Exception:
                logger.exception('scdata_sync: 重新對應任務獎勵藍圖失敗')
        if key == 'vehicles' and not errors:
            # 同名變體的系統說明（見 src/models/item.py 的 VehicleMaster.apply_system_notes）
            try:
                logger.info('scdata_sync: 艦船系統說明更新 %d 筆', VehicleMaster.apply_system_notes())
            except Exception:
                logger.exception('scdata_sync: 艦船系統說明更新失敗')

    elif key in SCUNPACKED_JOBS:
        # scunpacked-data 是公開靜態檔案，不用 token、沒有速率限制
        for resource in SCUNPACKED_JOBS[key]:
            try:
                stats.append(_sync_scunpacked_resource(client('github'), resource, run_id, stamp))
            except Exception as err:
                logger.exception('scdata_sync: scunpacked %s 失敗', resource)
                errors.append(f'scunpacked:{resource}: {err}')
        if key == 'locations' and not errors:
            # 上層、所屬星系要整份寫完才算得出來（見 src/models/starmap.py）
            _report(force=True, phase='整理上下層與所屬星系')
            logger.info('scdata_sync: 地點上下層更新 %d 筆', Starmap.rebuild_hierarchy())
            logger.info('scdata_sync: 地點「可存放」更新 %d 筆', Starmap.apply_storage())

    elif key == 'uex':
        # 後台「資料同步排程」頁設定的 token 優先，沒有就用環境變數 UEX_API_TOKEN
        uex_token = UexToken.get()
        if not uex_token:
            logger.warning('scdata_sync: 沒有 UEX token，跳過 UEX 同步。'
                           '到 https://uexcorp.space/api/apps 建 app 取得免費 token')
            return stats, ['uex: 未設定 UEX token，略過'], None
        for resource in UEX_RESOURCES:
            try:
                stats.append(_sync_uex_resource(client('uex', token=uex_token),
                                                resource, run_id, stamp))
            except Exception as err:
                logger.exception('scdata_sync: UEX %s 失敗', resource)
                errors.append(f'uex:{resource}: {err}')

    if key in visibility.SYNC_JOB_DATASETS:
        # 「玩家頁面顯示」：依名稱自動判斷，再套上後台的手動設定（見 src/models/visibility.py）
        try:
            _report(force=True, phase='整理玩家頁面顯示')
            logger.info('scdata_sync: %s 玩家頁面顯示更新 %d 筆', key, visibility.apply_for_job(key))
        except Exception:
            logger.exception('scdata_sync: %s 整理玩家頁面顯示失敗', key)

    return stats, errors, not errors


def _sum_stats(stats: list) -> dict:
    out = {}
    for s in stats:
        for k in ('seen', 'written', 'retired'):
            if isinstance(s.get(k), (int, float)):
                out[k] = out.get(k, 0) + s[k]
    return out


def _do_sync(jobs=None, translations_only: bool = False) -> dict:
    """同步的核心邏輯：依序跑指定的同步項目，寫入 sync_runs 與各項目的上次結果。

    每一項各自拿自己的鎖（job_lock_key），拿不到代表那一項已經有人在跑，略過它、
    其他項目照跑——所以不同的 Celery 任務可以同時同步不同的項目。

    刻意是純函式而不是 Celery task —— 這樣 `sync_scdata`（走 Celery 的
    retry 語意）與部署後的翻譯補跑可以共用同一份邏輯。

    jobs：同步項目 key 清單（見 src/models/sync_schedule.py 的 SYNC_JOBS），
    None = 全部；會照 SYNC_JOBS 的順序執行（翻譯最先）。
    translations_only：只同步翻譯（部署後資料庫還沒有翻譯時，心跳會自動跑一次）。
    """
    global _progress_job
    if translations_only:
        jobs = ['translations']
    requested = list(JOB_KEYS if jobs is None else jobs)
    unknown = [k for k in requested if k not in JOB_KEYS]
    if unknown:
        raise ValueError(f'未知的同步項目: {", ".join(map(str, unknown))}')
    jobs = order_jobs(requested)

    run_id = str(uuidlib.uuid4())
    started = datetime.utcnow()
    stats: list = []
    errors: list = []
    skipped: list = []
    busy: list = []
    ran: list = []

    logger.info('scdata_sync: 開始 run_id=%s jobs=%s', run_id, jobs)

    clients: dict = {}
    try:
        for key in jobs:
            with sync_lock(run_id, job_lock_key(key)) as acquired:
                if not acquired:
                    # 這一項已經有另一個任務在跑（例如排程跟手動同步撞在一起）
                    logger.info('scdata_sync: %s 已在同步中，略過', key)
                    busy.append(key)
                    continue
                ran.append(key)
                job_started = datetime.utcnow()
                SyncJobs.mark_started(key, run_id, job_started)
                _progress_job = key
                try:
                    job_stats, job_errors, ok = _run_job(key, run_id, job_started, clients)
                finally:
                    _progress_job = None
                stats += job_stats
                if ok is None:
                    skipped.append(key)
                else:
                    errors += job_errors
                SyncJobs.record_result(key, run_id, job_started, datetime.utcnow(), ok,
                                       error='；'.join(job_errors), stats=_sum_stats(job_stats))
    finally:
        for c in clients.values():
            try:
                c.close()
            except Exception:
                pass

    if not ran:
        return {'skipped': True, 'reason': 'already_running', 'jobs': jobs, 'busy': busy}

    finished = datetime.utcnow()
    summary = {
        '_id': run_id,
        'started_at': started,
        'finished_at': finished,
        'duration_s': round((finished - started).total_seconds(), 1),
        'jobs': ran,
        'skipped_jobs': skipped,
        'busy_jobs': busy,
        # 舊欄位（歷史紀錄頁、既有查詢用）
        'resources': [k for k in ran if k in WIKI_RESOURCES],
        'with_uex': 'uex' in ran and 'uex' not in skipped,
        'with_scunpacked': 'mining' in ran,
        'with_translations': 'translations' in ran,
        'translations_only': translations_only,
        'stats': stats,
        'errors': errors,
        'ok': not errors,
    }
    get_db()['sync_runs'].insert_one(summary)

    logger.info('scdata_sync: 結束 %.1fs errors=%d', summary['duration_s'], len(errors))
    return {'run_id': run_id, 'duration_s': summary['duration_s'],
            'ok': summary['ok'], 'errors': errors, 'jobs': ran, 'busy': busy,
            'stats': [{k: s[k] for k in ('resource', 'seen', 'written', 'retired')
                       if k in s} for s in stats]}


@celery_app.task(name='tasks.scdata_sync.sync_scdata', bind=True, max_retries=2)
def sync_scdata(self, jobs=None):
    """同步指定的項目（手動「立即同步」與排程到期都派送這支，一般一次一項）。

    :param jobs: 同步項目 key 清單，預設全部（見 src/models/sync_schedule.py 的 SYNC_JOBS）
    """
    try:
        return _do_sync(jobs=jobs)
    except ScDataError as exc:
        # 上游整體不可用 → 退避重試，不要寫一筆假的成功紀錄。
        # 注意：這條路徑只在透過 .delay() 派送時有效
        #（Task.retry 在 called_directly 時會直接重拋原例外）。
        logger.error('scdata_sync: 上游 API 不可用: %s', exc)
        raise self.retry(exc=exc, countdown=600)
    finally:
        # 沒拿到鎖而略過的項目也要把「排隊中」標記清掉
        for key in order_jobs(JOB_KEYS if jobs is None else jobs):
            SyncJobs.clear_queued(key, getattr(self.request, 'id', None))


def dispatch_jobs(keys, by: str = None) -> tuple:
    """把同步項目各自派成一個 Celery 任務（可以同時跑），回傳 (已派送, 略過)。

    正在跑的、或已經排隊等 worker 的項目不重複派送。
    """
    keys = order_jobs(keys)
    running = set(running_jobs())
    now = datetime.utcnow()
    jobs = {j['key']: j for j in SyncJobs.all()}
    sent, skipped = [], []
    for key in keys:
        if key in running or SyncJobs.is_queued(jobs.get(key) or {}, now):
            skipped.append(key)
            continue
        result = sync_scdata.apply_async(kwargs={'jobs': [key]})
        SyncJobs.mark_queued(key, getattr(result, 'id', None), now, by)
        sent.append(key)
    return sent, skipped


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
    if 'translations' in running_jobs():
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

    排程存在 DB（src/models/sync_schedule.py 的 SyncJobs，每個資料庫一筆），可在
    後台「資料同步排程」頁個別編輯，不用改 celeryconfig.py、也不用重啟 worker/beat。
    這支只負責挑出到期的項目、各自派成一個 sync_scdata 任務（不同項目同時跑，
    同時跑幾個看 worker 的 concurrency），本身不做同步、很快就結束。

    到期判斷各自依「最後一次嘗試」（失敗走較短的 backoff）；正在跑或已經在排隊
    的項目不重複派送。
    """
    # 資料庫還沒有任何翻譯（剛部署、或 sc_translations 被清掉）時，不等排程到期，
    # 先只同步翻譯——否則全站中文化要等下一次排程（預設一週）才會出現。
    # 失敗的話 30 分鐘後才再試，不要每 5 分鐘打一次 GitHub。
    bootstrap = _translations_bootstrap()
    if bootstrap is not None:
        return bootstrap

    due = SyncJobs.due_jobs()
    if not due:
        logger.debug('check_and_run_scheduled_sync: 沒有到期的同步項目')
        return {'skipped': True, 'reason': 'not_due'}

    sent, skipped = dispatch_jobs([k for k, _ in due], by='schedule')
    logger.info('check_and_run_scheduled_sync: 派送 %s（略過進行中／排隊中的 %s）',
                '、'.join(f'{k}（{reason}）' for k, reason in due if k in sent) or '—',
                '、'.join(skipped) or '—')
    return {'skipped': not sent, 'dispatched': sent, 'busy': skipped}
