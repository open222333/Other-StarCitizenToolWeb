"""星際公民遊戲資料同步（Celery 任務）。

抓取邏輯在 src/scdata.py，這裡只負責寫入 MongoDB 與批次紀錄。

兩個關鍵設計：

1. **永不刪除。** 每輪同步有一個 run_id；沒被這輪碰到的文件會被標
   is_current=False + retired_at，不會刪掉。舊 patch 移除的物品仍留在 DB，
   這樣 inventory.item_id 的外鍵不會斷。查主檔時記得加 is_current=True。

2. **版本快照。** 每個 patch 額外寫一份 *_versions（_id 是 uuid@version，
   $setOnInsert 只寫一次），用來比對 patch 之間的數值變動。

手動觸發：
    docker compose exec worker python -c \\
      "from tasks.scdata_sync import sync_scdata; print(sync_scdata())"
"""

import logging
import uuid as uuidlib
from datetime import datetime

from pymongo import UpdateOne

from src import UEX_API_TOKEN
from src.celery_app import celery_app
from src.mongo import get_db
from src.scdata import (BULK_SIZE, UEX_RESOURCES, WIKI_RESOURCES, ScDataError,
                        build_client, uex_doc_id, uex_rows, wiki_rows)

logger = logging.getLogger(__name__)


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


@celery_app.task(name='tasks.scdata_sync.sync_scdata', bind=True, max_retries=2)
def sync_scdata(self, resources=None, with_uex: bool = True):
    """同步遊戲主檔。

    :param resources: 要同步的資源清單，預設全部（items / vehicles / commodities）
    :param with_uex: 是否同步 UEX 價格（沒有 UEX_API_TOKEN 會自動跳過）
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

    try:
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

    except ScDataError as exc:
        # 上游整體不可用 → 退避重試，不要寫一筆假的成功紀錄
        logger.error('scdata_sync: 上游 API 不可用: %s', exc)
        raise self.retry(exc=exc, countdown=600)

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
