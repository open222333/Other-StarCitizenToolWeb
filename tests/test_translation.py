"""遊戲文字翻譯（sc_translations）—— 全站中文化的唯一來源。

涵蓋：翻譯包格式解析、寫入（串流、沒變不重寫、移除不存在的 key、人工條目
不被覆蓋）、快取隨同步版本作廢、各領域的查法（src/sc_zh.py）、同步任務的
保護與部署後自動補跑、公開的 /item/translations。
"""
from datetime import datetime

import pytest

from src.models import translation as T
from src.mongo import get_db
from src import scdata
import src.sc_zh as Z


# ═══════════════════════════════════════════════════════
#  解析
# ═══════════════════════════════════════════════════════

def test_strip_english_formats():
    # 名稱類：「English\n中文」
    assert T.strip_english('Avenger Stalker\\n復仇者 追獵', 'Avenger Stalker') == '復仇者 追獵'
    # 地點／陣營：「中文（English）」
    assert T.strip_english('羅威爾（Lorville）', 'Lorville') == '羅威爾'
    # 翻譯包前半的英文跟遊戲英文表不一字不差，仍然是「英文\n翻譯」格式
    assert T.strip_english('Heph (Raw)\\n火神石（原礦）', 'Hephaestanite (R)') == '火神石（原礦）'
    # 說明文字裡的 \n 是真正的換行，不能切
    desc = '製造商：聖盾動力\\n定位：攔截機'
    assert T.strip_english(desc, 'Manufacturer: Aegis') == desc
    # 只有翻譯
    assert T.strip_english('截擊', 'Interceptor') == '截擊'


def test_iter_translation_ini_strips_flags_bom_and_comments():
    text = '﻿vehicle_class_interceptor=截擊\n; 註解\nPU_Foo,P=喔\nbroken line\n'
    assert dict(scdata.iter_translation_ini(text)) == {
        'vehicle_class_interceptor': '截擊', 'PU_Foo': '喔'}


def test_iter_translation_entries_joins_english_and_translation():
    labels = {'﻿vehicle_class_interceptor': 'Interceptor',
              'Stanton1_Lorville': 'Lorville',
              'only_english,P': 'Only English'}
    ini = ('vehicle_class_interceptor=截擊\n'
           'Stanton1_Lorville=羅威爾（Lorville）\n'
           'only_in_pack=Pack Name\\n包裡才有\n'
           'no_english_at_all=純中文\n')
    entries = {k: t for k, t, _ in scdata.iter_translation_entries(
        scdata.normalize_labels(labels), ini, 'zh-TW')}
    assert entries['vehicle_class_interceptor'] == {'en': 'Interceptor', 'zh-TW': '截擊'}
    assert entries['Stanton1_Lorville'] == {'en': 'Lorville', 'zh-TW': '羅威爾'}
    assert entries['only_english'] == {'en': 'Only English'}, '英文表的 ,P 旗標也要去掉'
    # 翻譯包有、英文表沒有：英文取中英並列格式的前半
    assert entries['only_in_pack'] == {'en': 'Pack Name', 'zh-TW': '包裡才有'}
    # 兩邊都沒有英文就不收（無從反查）
    assert 'no_english_at_all' not in entries


# ═══════════════════════════════════════════════════════
#  寫入
# ═══════════════════════════════════════════════════════

def _entries(d):
    return ((k, {'en': en, 'zh-TW': zh}, None) for k, (en, zh) in d.items())


def test_replace_source_skips_unchanged_and_removes_stale(client):
    now = datetime.utcnow()
    first = T.replace_source(_entries({'a': ('A', '甲'), 'b': ('B', '乙')}), T.SOURCE_GAME, now)
    assert first == {'seen': 2, 'written': 2, 'retired': 0}

    again = T.replace_source(_entries({'a': ('A', '甲'), 'b': ('B', '乙')}), T.SOURCE_GAME, now)
    assert again['written'] == 0, '內容沒變不該重寫'

    changed = T.replace_source(_entries({'a': ('A', '甲改')}), T.SOURCE_GAME, now)
    assert changed == {'seen': 1, 'written': 1, 'retired': 1}
    assert get_db()[T.COLLECTION].find_one({'_id': 'b'}) is None
    assert get_db()[T.COLLECTION].find_one({'_id': 'a'})['text']['zh-TW'] == '甲改'


def test_game_sync_does_not_touch_manual_entries(client):
    now = datetime.utcnow()
    T.sync_manual(now)
    manual_before = T.count(T.SOURCE_MANUAL)
    assert manual_before > 0
    T.replace_source(_entries({'a': ('A', '甲')}), T.SOURCE_GAME, now)
    T.replace_source(_entries({}), T.SOURCE_GAME, now)
    assert T.count(T.SOURCE_MANUAL) == manual_before


def test_cache_is_invalidated_by_a_new_sync_version(client, seed_translations):
    seed_translations({'Stanton1_Lorville': ('Lorville', '羅威爾')})
    assert Z.location_name_zh('Lorville') == '羅威爾'

    # 同步寫入新翻譯＋新版本 → 不用重啟 process 就查得到新值
    T.replace_source(_entries({'Stanton1_Lorville': ('Lorville', '新譯名')}), T.SOURCE_GAME,
                     datetime.utcnow())
    assert Z.location_name_zh('Lorville') == '羅威爾', '版本還沒換之前用快取'
    T.mark_synced('v2', datetime.utcnow())
    assert Z.location_name_zh('Lorville') == '新譯名'


def test_untranslated_text_counts_as_no_translation(client, seed_translations):
    seed_translations({'Stanton1_Foo': ('Foo', 'Foo')})
    assert Z.location_name_zh('Foo') is None


# ═══════════════════════════════════════════════════════
#  各領域的查法
# ═══════════════════════════════════════════════════════

def test_location_lookup_prefers_location_keys_and_ignores_case(client, seed_translations):
    seed_translations({
        'mission_location_stanton_0061': ('Grim HEX', '任務用的譯名'),
        'Stanton1_Lorville': ('Lorville', '羅威爾'),
        'stanton2_housing_grimhex': ('Grim HEX', '六角灣'),
        'some_mission_text_lorville': ('Lorville', '不該被選到'),
        'AsteroidCluster_MiningBase_Stanton01_Medium_07': ('Mining Base #365-YNZ', '採礦基地 #365-YNZ'),
    })
    assert Z.location_name_zh('Grim Hex') == '六角灣', 'StantonN_ 系列優先於任務地點，不分大小寫'
    assert Z.location_name_zh('Lorville') == '羅威爾'
    assert Z.location_name_zh('Mining Base #365-YNZ') == '採礦基地 #365-YNZ'
    assert Z.location_name_zh('Nowhere') is None


def test_known_location_names(client, seed_translations):
    seed_translations({
        'Stanton': ('Stanton', '斯坦頓'),
        'Stanton1_Lorville': ('Lorville', '羅威爾'),
        'Stanton1_Lorville_Desc': ('Lorville is the capital…', '說明'),
        'Pyro1_L1': ('PYR1 L1', None),
    })
    names = Z.known_location_names()
    assert names == {'Stanton': '斯坦頓', 'Lorville': '羅威爾', 'PYR1 L1': None}


def test_item_lookup_prefers_class_name(client, seed_translations):
    seed_translations({
        'item_NameAEGS_Idris_Mav_Fixed_CIV': ('Fixed Mav Thruster', '聯合式機動推進器'),
        'item_Name_other_same_english': ('Fixed Mav Thruster', '別的譯名'),
    })
    assert Z.item_name_zh('Fixed Mav Thruster', 'AEGS_Idris_Mav_Fixed_CIV') == '聯合式機動推進器'
    assert Z.item_name_zh('Unknown', 'NOPE') is None


def test_mining_lookups(client, seed_translations):
    seed_translations({
        'items_commodities_aluminum_ore': ('Aluminum (Ore)', '鋁礦石'),
        'items_commodities_ice': ('Ice', '冰'),
    })
    assert Z.mining_resource_name_zh('Ore_Aluminum', 'Aluminum (Ore)') == '鋁礦石'
    # 原名查不到時退回去掉 "Raw " 前綴的寫法
    assert Z.mining_resource_name_zh('Raw_Ice', 'Raw Ice') == '冰'
    # 沒給名稱時用 resource_key 還原
    assert Z.mining_resource_name_zh('Raw_Ice') == '冰'
    # 礦床：岩石分類是人工條目，單一礦物的礦床用礦物的查法
    assert Z.mining_deposit_name_zh('Granite Deposit') == '花崗岩礦床'
    assert Z.mining_deposit_name_zh('Aluminum (Ore)') == '鋁礦石'


def test_blueprint_types_are_manual_entries(client, seed_translations):
    seed_translations({})
    assert Z.blueprint_type_zh('WeaponGun') == '載具武器'
    names = Z.blueprint_type_names()
    assert names['PowerPlant'] == '發電機' and len(names) == 27


def test_manual_entries_are_written_at_startup(app):
    """app 啟動（ensure_indexes）就會寫人工條目，不用等第一次同步。"""
    from src.mongo import ensure_indexes
    ensure_indexes()
    assert Z.blueprint_type_zh('WeaponGun') == '載具武器'


# ═══════════════════════════════════════════════════════
#  同步任務
# ═══════════════════════════════════════════════════════

@pytest.fixture
def sync_mod():
    import tasks.scdata_sync as m
    return m


def _fake_sources(monkeypatch, sync_mod, labels, ini):
    monkeypatch.setattr(sync_mod, 'fetch_scunpacked_rows',
                        lambda client, path, expect=list: labels)
    monkeypatch.setattr(sync_mod, 'fetch_translation_ini', lambda client: ini)


def _big_sources(n=1200):
    labels = {f'key_{i}': f'English {i}' for i in range(n)}
    labels['vehicle_class_interceptor'] = 'Interceptor'
    ini = ''.join(f'key_{i}=中文 {i}\n' for i in range(n)) + 'vehicle_class_interceptor=截擊\n'
    return labels, ini


def test_sync_translations_writes_everything(client, sync_mod, monkeypatch):
    labels, ini = _big_sources()
    _fake_sources(monkeypatch, sync_mod, labels, ini)
    result = sync_mod._sync_translations(None, 'run-1', datetime.utcnow())
    assert result['resource'] == 'translations' and result['seen'] == 1201
    assert result['manual'] > 0
    assert T.status()['version'] == 'run-1'
    assert Z.vehicle_role_zh('Interceptor') == '截擊'


def test_sync_translations_refuses_a_truncated_download(client, sync_mod, monkeypatch):
    labels, ini = _big_sources(2000)
    _fake_sources(monkeypatch, sync_mod, labels, ini)
    sync_mod._sync_translations(None, 'run-1', datetime.utcnow())

    # 翻譯包只抓到一小段（例如 GitHub 回了半份）→ 整批跳過，不能把九成翻譯刪掉
    _fake_sources(monkeypatch, sync_mod, labels, 'key_0=中文 0\n' * 10)
    with pytest.raises(sync_mod.ScDataError):
        sync_mod._sync_translations(None, 'run-2', datetime.utcnow())
    assert T.count(T.SOURCE_GAME) == 2001
    assert T.status()['version'] == 'run-1'


def test_heartbeat_bootstraps_translations_once(client, sync_mod, monkeypatch):
    calls = []
    monkeypatch.setattr(sync_mod, '_do_sync', lambda **kw: calls.append(kw) or {'ok': True})

    sync_mod.check_and_run_scheduled_sync()
    assert calls == [{'translations_only': True}]

    # 30 分鐘內不重試（失敗時不要每 5 分鐘打一次 GitHub）
    sync_mod.check_and_run_scheduled_sync()
    assert calls[1:] != [{'translations_only': True}]


def test_translations_only_runs_do_not_move_the_schedule(client, sync_mod):
    now = datetime.utcnow()
    get_db()['sync_runs'].insert_one({'_id': 't', 'started_at': now, 'finished_at': now,
                                      'ok': True, 'translations_only': True})
    due, reason = sync_mod._is_due()
    assert (due, reason) == (True, 'never_run')


# ═══════════════════════════════════════════════════════
#  /item/translations（公開）
# ═══════════════════════════════════════════════════════

def test_translations_endpoint_is_public(client, seed_translations):
    seed_translations({'Stanton1_Lorville': ('Lorville', '羅威爾')})
    body = client.get('/item/translations?domain=location&text=Lorville&text=Nowhere').get_json()
    assert body == {'success': True, 'data': {'Lorville': '羅威爾'}}


def test_translations_endpoint_full_lists(client, seed_translations):
    seed_translations({'Stanton1_Lorville': ('Lorville', '羅威爾')})
    types = client.get('/item/translations?domain=blueprint_type').get_json()['data']
    assert types['WeaponGun'] == '載具武器'
    locations = client.get('/item/translations?domain=location').get_json()['data']
    assert locations == {'Lorville': '羅威爾'}


def test_translations_endpoint_validates_input(client):
    assert client.get('/item/translations?domain=nope&text=a').status_code == 400
    assert client.get('/item/translations?domain=item').status_code == 400
    many = '&'.join(f'text=t{i}' for i in range(301))
    assert client.get(f'/item/translations?domain=item&{many}').status_code == 400


def test_ensure_indexes_never_tests_database_truthiness(client):
    """pymongo 的 Database 物件不能做 bool()（會丟 NotImplementedError）——
    `db = db or get_db()` 這種寫法在 mongomock 會過、正式環境 api 直接起不來
    （實際發生過：容器 unhealthy，log 一直印 "Database objects do not implement
    truth value testing"）。這裡用一個同樣禁止 bool() 的包裝確認不會再犯。"""
    real = get_db()

    class StrictDatabase:
        def __bool__(self):
            raise NotImplementedError('Database objects do not implement truth value testing')

        def __getitem__(self, name):
            return real[name]

    T.ensure_indexes(StrictDatabase())
    import pymongo
    fake = pymongo.MongoClient('mongodb://127.0.0.1:1', connect=False)['x']
    with pytest.raises(NotImplementedError):
        bool(fake)   # 確認假設本身：真的 pymongo Database 確實禁止 bool()
