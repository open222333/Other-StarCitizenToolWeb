"""Discord 綁定必須經過綁定碼驗證的迴歸測試。

原本的漏洞：`/bind` 的 handle 是自由文字，`DiscordBinding.bind()` 只檢查
長度就寫進 DB，而 bot 之後把那個 handle 當成身分用
（`/stock scope:我的個人庫`、`/remove`）。所以任何 Discord 使用者打
`/bind handle:別人的遊戲ID` 就能看光那個人的個人庫、把它清空 ——
紀錄上的 `player` 還是被害者，不需要任何管理員操作。

現在綁定需要玩家在「要密碼登入的網頁」產生的一次性碼：密碼登入就是
那個「證明你是這個遊戲ID的人」的環節。這支測試鎖住：
沒有碼不能綁、碼是一次性的、過期無效、碼不會從任何 API 洩漏出去。
"""
from datetime import datetime, timedelta

import pytest

from src.models.inventory import DiscordBinding, StockError
from src.models.player import Player


SCOPE = 'test-scope'


@pytest.fixture
def player():
    pid = Player.create(player_name='Tom', star_citizen_id='Tom_SC', password='hunter22')
    return Player.find_by_id(pid)


def _issue(player_doc):
    return Player.issue_discord_code(player_doc['_id'])['code']


# ── 沒有有效綁定碼就不能綁 ────────────────────────────────────

def test_bind_without_code_is_rejected(player):
    """這就是原本的攻擊路徑：直接宣稱別人的 handle。"""
    with pytest.raises(StockError) as exc:
        DiscordBinding.bind('攻擊者123', 'Tom_SC', SCOPE)
    assert '綁定碼' in str(exc.value)
    assert DiscordBinding.get('攻擊者123') is None


def test_bind_with_wrong_code_is_rejected(player):
    _issue(player)
    with pytest.raises(StockError):
        DiscordBinding.bind('攻擊者123', 'Tom_SC', SCOPE, code='WRONGCOD')
    assert DiscordBinding.get('攻擊者123') is None


def test_bind_with_another_players_code_is_rejected(player):
    """A 的碼不能用來綁 B 的 handle。"""
    other_id = Player.create(player_name='Bob', star_citizen_id='Bob_SC')
    other_code = Player.issue_discord_code(other_id)['code']

    with pytest.raises(StockError):
        DiscordBinding.bind('攻擊者123', 'Tom_SC', SCOPE, code=other_code)
    assert DiscordBinding.get('攻擊者123') is None


def test_bind_for_unknown_handle_is_rejected(player):
    """名冊上沒有這個遊戲ID —— 不管碼是什麼都不該綁定成功。"""
    code = _issue(player)
    with pytest.raises(StockError):
        DiscordBinding.bind('某人', '不存在的ID', SCOPE, code=code)


def test_bind_with_expired_code_is_rejected(player):
    from src.mongo import get_db
    _issue(player)
    # 直接把到期時間改成過去，模擬 10 分鐘後才拿去用
    get_db()['players'].update_one(
        {'star_citizen_id': 'Tom_SC'},
        {'$set': {'discord_bind_code_expires_at': datetime.utcnow() - timedelta(minutes=1)}})
    code = get_db()['players'].find_one({'star_citizen_id': 'Tom_SC'})['discord_bind_code']

    with pytest.raises(StockError):
        DiscordBinding.bind('某人', 'Tom_SC', SCOPE, code=code)


# ── 正常流程 ──────────────────────────────────────────────────

def test_bind_with_valid_code_succeeds(player):
    code = _issue(player)
    doc = DiscordBinding.bind('discord-1', 'Tom_SC', SCOPE, code=code,
                              discord_name='tom#1')
    assert doc['handle'] == 'Tom_SC'
    assert DiscordBinding.require_handle('discord-1') == 'Tom_SC'


def test_code_is_single_use(player):
    """同一組碼不能綁第二個 Discord 帳號。"""
    code = _issue(player)
    DiscordBinding.bind('discord-1', 'Tom_SC', SCOPE, code=code)

    with pytest.raises(StockError):
        DiscordBinding.bind('discord-2', 'Tom_SC', SCOPE, code=code)
    assert DiscordBinding.get('discord-2') is None


def test_code_is_case_and_dash_tolerant(player):
    """玩家從畫面上抄碼，小寫或多打一個連字號不該被當成錯誤。"""
    code = _issue(player)
    doc = DiscordBinding.bind('discord-1', 'Tom_SC', SCOPE,
                              code=f'{code[:4].lower()}-{code[4:].lower()}')
    assert doc['handle'] == 'Tom_SC'


def test_reissue_invalidates_the_previous_code(player):
    old = _issue(player)
    _issue(player)                      # 重新產生
    with pytest.raises(StockError):
        DiscordBinding.bind('discord-1', 'Tom_SC', SCOPE, code=old)


def test_rebinding_the_same_handle_removes_the_old_binding(player):
    """玩家換 Discord 帳號：同一個 handle 不該同時掛在兩個帳號上，
    否則「誰動了我的庫存」查不清楚。"""
    DiscordBinding.bind('discord-old', 'Tom_SC', SCOPE, code=_issue(player))
    DiscordBinding.bind('discord-new', 'Tom_SC', SCOPE, code=_issue(player))

    assert DiscordBinding.get('discord-new')['handle'] == 'Tom_SC'
    assert DiscordBinding.get('discord-old') is None


def test_issue_code_on_deleted_player_returns_none(player):
    Player.soft_delete(player['_id'])
    assert Player.issue_discord_code(player['_id']) is None


def test_issue_code_with_malformed_id_returns_none():
    assert Player.issue_discord_code('not-an-objectid') is None


# ── 碼不能從任何 API 洩漏 ─────────────────────────────────────

def test_code_never_appears_in_serialized_player(player):
    """看得到名冊的人（後台 viewer、或玩家自己的 /player/me）如果能讀到
    別人的有效綁定碼，就等於這道驗證不存在。"""
    _issue(player)

    for doc in [Player.find_by_id(player['_id']),
                Player.find_by_star_citizen_id('Tom_SC'),
                *Player.find_all()]:
        assert 'discord_bind_code' not in doc
        assert 'discord_bind_code_expires_at' not in doc


def test_api_me_does_not_expose_the_code(client, player):
    _issue(player)
    token = client.post('/player/login', json={
        'star_citizen_id': 'Tom_SC', 'password': 'hunter22'}).get_json()['token']
    data = client.get('/player/me',
                      headers={'Authorization': f'Bearer {token}'}).get_json()['data']
    assert 'discord_bind_code' not in data


def test_api_issue_code_returns_a_usable_code(client, player):
    token = client.post('/player/login', json={
        'star_citizen_id': 'Tom_SC', 'password': 'hunter22'}).get_json()['token']

    resp = client.post('/player/me/discord-code',
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body['code']) == 8
    assert body['star_citizen_id'] == 'Tom_SC'

    # 這組碼真的能完成綁定
    doc = DiscordBinding.bind('discord-1', 'Tom_SC', SCOPE, code=body['code'])
    assert doc['handle'] == 'Tom_SC'


def test_api_issue_code_requires_player_token(client, player, auth_headers):
    """後台 admin token 不能替玩家產生綁定碼 —— 那會讓管理員能綁走任何人的
    Discord。要綁定就得知道玩家自己的密碼。"""
    assert client.post('/player/me/discord-code').status_code == 401
    assert client.post('/player/me/discord-code',
                       headers=auth_headers).status_code == 403
