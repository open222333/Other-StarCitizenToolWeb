"""軟刪除玩家的還原路徑，以及「遊戲ID不再被軟刪資料卡死」的迴歸測試。

原本的問題（審查報告 B6）：
`players.star_citizen_id` 的唯一索引不是 partial index，軟刪除的文件仍然
佔著那個遊戲ID。所以成員被移除之後：
  1. 他自助註冊 → 註冊前的檢查會過濾 deleted_at，說「這個ID可以用」
  2. 接著 insert 撞唯一索引 → 使用者看到「這個遊戲ID已經被註冊過了」
  3. 但後台名冊查不到這個人（軟刪的不顯示），沒有人能解釋
而且全專案沒有任何還原路由，誤刪之後只能進資料庫手改。

這支測試鎖住兩件事：partial 索引讓軟刪的ID可以重新使用、還原路徑存在
且會擋住「同ID已經有一筆使用中資料」的衝突。
"""
import pytest

from src.models.player import Player, PlayerError
from src.mongo import ensure_indexes


@pytest.fixture
def indexed_db():
    """建立索引 —— conftest 的 clean_db 每個測試後會 drop collection（索引也跟著消失），
    所以需要索引語意的測試要自己先建一次。"""
    ensure_indexes()
    yield


# ── partial 唯一索引 ──────────────────────────────────────────

def test_active_duplicate_scid_is_still_rejected(indexed_db):
    """使用中的玩家仍然不能有兩筆同遊戲ID —— partial 只放寬軟刪的那些。"""
    Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    with pytest.raises(PlayerError):
        Player.create(player_name='Tom 分身', star_citizen_id='Tom_SC')


def test_soft_deleted_scid_can_be_registered_again(indexed_db):
    """這就是 B6 的核心：移除成員之後，那個遊戲ID要能重新註冊。"""
    pid = Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    assert Player.soft_delete(pid) is True

    # 舊版在這一行會丟 DuplicateKeyError（被 model 轉成 PlayerError）
    new_pid = Player.create(player_name='Tom', star_citizen_id='Tom_SC',
                            password='hunter22')
    assert new_pid != pid
    assert Player.find_by_star_citizen_id('Tom_SC')['_id'] == new_pid


def test_two_soft_deleted_docs_with_same_scid_are_allowed(indexed_db):
    """同一個ID被移除兩次（註冊→移除→再註冊→再移除）也不能卡住。

    非 partial 索引下，第二筆軟刪文件會跟第一筆撞鍵。
    """
    first = Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    Player.soft_delete(first)
    second = Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    Player.soft_delete(second)

    assert Player.find_by_star_citizen_id('Tom_SC') is None
    scids = [p['star_citizen_id'] for p in Player.find_all(include_deleted=True)]
    assert scids.count('Tom_SC') == 2


# ── Player.restore ───────────────────────────────────────────

def test_restore_brings_the_player_back(indexed_db):
    pid = Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    Player.soft_delete(pid)
    assert Player.find_by_star_citizen_id('Tom_SC') is None

    assert Player.restore(pid) is True
    back = Player.find_by_star_citizen_id('Tom_SC')
    assert back is not None
    assert back['_id'] == pid
    assert back['deleted_at'] is None


def test_restore_on_active_player_is_a_noop(indexed_db):
    """沒有被移除的玩家「還原」沒有意義，回 False 讓路由回 404。"""
    pid = Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    assert Player.restore(pid) is False


def test_restore_rejects_when_scid_is_taken_again(indexed_db):
    """移除後那個人又重新註冊了 —— 這時候還原舊資料會變成兩筆使用中的同ID，
    要給明確錯誤而不是 500。"""
    old = Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    Player.soft_delete(old)
    Player.create(player_name='Tom（新）', star_citizen_id='Tom_SC')

    with pytest.raises(PlayerError) as exc:
        Player.restore(old)
    assert 'Tom_SC' in str(exc.value)


def test_restore_with_malformed_id_returns_false():
    assert Player.restore('not-an-objectid') is False


def test_find_by_id_hides_deleted_unless_asked():
    pid = Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    Player.soft_delete(pid)
    assert Player.find_by_id(pid) is None
    assert Player.find_by_id(pid, include_deleted=True)['_id'] == pid


# ── API ───────────────────────────────────────────────────────

def test_restore_route_brings_player_back(client, auth_headers, indexed_db):
    pid = Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    client.delete(f'/player/{pid}', headers=auth_headers)

    resp = client.post(f'/player/{pid}/restore', headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    assert Player.find_by_star_citizen_id('Tom_SC') is not None


def test_restore_route_404_for_active_or_unknown_player(client, auth_headers, indexed_db):
    pid = Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    assert client.post(f'/player/{pid}/restore', headers=auth_headers).status_code == 404
    assert client.post('/player/deadbeefdeadbeefdeadbeef/restore',
                       headers=auth_headers).status_code == 404


def test_restore_route_409_when_scid_taken(client, auth_headers, indexed_db):
    old = Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    Player.soft_delete(old)
    Player.create(player_name='Tom（新）', star_citizen_id='Tom_SC')

    resp = client.post(f'/player/{old}/restore', headers=auth_headers)
    assert resp.status_code == 409
    assert 'Tom_SC' in resp.get_json()['message']


def test_list_players_hides_deleted_by_default(client, auth_headers, indexed_db):
    pid = Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    Player.soft_delete(pid)

    resp = client.get('/player/', headers=auth_headers)
    assert resp.get_json()['data'] == []


def test_list_players_can_include_deleted(client, auth_headers, indexed_db):
    """後台要能看到已移除的玩家才有辦法還原。"""
    pid = Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    Player.soft_delete(pid)

    rows = client.get('/player/?include_deleted=1', headers=auth_headers).get_json()['data']
    assert [r['_id'] for r in rows] == [pid]
    assert rows[0]['deleted_at'] is not None
    # 這條路徑一樣不能把密碼 hash 帶出去
    assert 'password' not in rows[0]


def test_restore_is_written_to_the_audit_log(client, auth_headers, indexed_db):
    """移除／還原成員是最需要能回溯的操作。"""
    from src.models.log import Log

    pid = Player.create(player_name='Tom', star_citizen_id='Tom_SC')
    client.delete(f'/player/{pid}', headers=auth_headers)
    client.post(f'/player/{pid}/restore', headers=auth_headers)

    actions = [row['action'] for row in Log.find_all()]
    assert 'delete_player' in actions
    assert 'restore_player' in actions
