"""後台 API 的權限矩陣回歸測試。

## 這支測試在防什麼

本專案有兩套身分體系，**共用同一把 JWT 金鑰**：

  - 後台帳號：`/auth/login`，identity = username，role 是 admin/operator/viewer
  - 玩家自助：`/player/login`，identity = `player:<scid>`，claim `type='player'`

`@jwt_required()` 只驗簽章 —— 它不看 identity 格式、也不看自訂 claim。
所以任何只掛 `@jwt_required()` 的後台路由，玩家自助 token 都能直接通過。

這個洞真的發生過：`/player/*`、`/blueprint/*`、`/log/` 共 11 支路由曾經只有
`@jwt_required()`，任何註冊過的玩家都能讀全公會 PII、改／軟刪任何玩家資料
（軟刪後對方永遠無法登入）、讀完整後台稽核日誌。

下面的矩陣把「每一支後台路由 × 四種身分」全部跑一遍。新增後台路由若忘記掛
`admin_api()`，`test_no_admin_route_is_left_unguarded` 會直接失敗。
"""
import pytest

from src.permissions import READ_ROLES, WRITE_ROLES

# ═══════════════════════════════════════════════════════════
#  身分 fixtures
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def make_user(client):
    """建立任意角色的後台帳號並回傳它的 access token。"""
    from src.models.user import User
    from src.models.user_template import UserTemplate

    def _make(username, role):
        tid = UserTemplate.ensure_defaults()
        User.create(username, 'Passw0rd!23', role=role, template_id=tid)
        resp = client.post('/auth/login', json={
            'username': username, 'password': 'Passw0rd!23',
        })
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()['token']

    return _make


@pytest.fixture
def viewer_headers(make_user):
    return {'Authorization': f"Bearer {make_user('viewer_user', 'viewer')}"}


@pytest.fixture
def operator_headers(make_user):
    return {'Authorization': f"Bearer {make_user('operator_user', 'operator')}"}


@pytest.fixture
def player_headers(client):
    """註冊 + 登入一個玩家自助帳號，回傳它的 Bearer header。

    這是本檔案的重點身分 —— 它拿到的是一個簽章完全合法的 JWT，
    所以 @jwt_required() 擋不住它。
    """
    reg = client.post('/player/register', json={
        'nickname': 'TestPilot',
        'star_citizen_id': 'TestPilot',
        'password': 'player-pw-123',
    })
    assert reg.status_code == 201, reg.get_json()

    login = client.post('/player/login', json={
        'star_citizen_id': 'TestPilot', 'password': 'player-pw-123',
    })
    assert login.status_code == 200, login.get_json()
    return {'Authorization': f"Bearer {login.get_json()['token']}"}


# ═══════════════════════════════════════════════════════════
#  路由矩陣
# ═══════════════════════════════════════════════════════════

# (method, path, 允許的角色)
#   READ_ROLES  = admin / operator / viewer
#   WRITE_ROLES = admin / operator
_OID = '507f1f77bcf86cd799439011'          # 格式正確但不存在的 ObjectId

ADMIN_ROUTES = [
    # 玩家名冊（後台端，可操作任何玩家）
    ('GET',    '/player/',            READ_ROLES),
    ('GET',    f'/player/{_OID}',     READ_ROLES),
    ('POST',   '/player/',            WRITE_ROLES),
    ('PUT',    f'/player/{_OID}',     WRITE_ROLES),
    ('DELETE', f'/player/{_OID}',     WRITE_ROLES),
    ('PUT',    f'/player/{_OID}/password', WRITE_ROLES),
    # 藍圖名冊（後台端）
    ('GET',    '/blueprint/',         READ_ROLES),
    ('GET',    f'/blueprint/{_OID}',  READ_ROLES),
    ('POST',   '/blueprint/',         WRITE_ROLES),
    ('PUT',    f'/blueprint/{_OID}',  WRITE_ROLES),
    ('DELETE', f'/blueprint/{_OID}',  WRITE_ROLES),
    # 稽核日誌
    ('GET',    '/log/',               READ_ROLES),
    # 庫存（寫入端）
    ('POST',   '/inventory/add',      WRITE_ROLES),
    ('POST',   '/inventory/remove',   WRITE_ROLES),
    ('POST',   '/inventory/move',     WRITE_ROLES),
    # 庫存全域異動紀錄（含操作者與備註，所以是後台專屬）
    ('GET',    '/inventory/history',  READ_ROLES),
    # 遊戲資料同步（後台設定頁專用，玩家端不會用到）
    ('GET',    '/item/sync-status',   READ_ROLES),
    ('GET',    '/item/sync-schedule', READ_ROLES),
    ('POST',   '/item/sync',          WRITE_ROLES),
    ('PUT',    '/item/sync-schedule', WRITE_ROLES),
]

_IDS = [f'{m} {p}' for m, p, _ in ADMIN_ROUTES]


def _call(client, method, path, headers=None):
    return client.open(path, method=method, headers=headers or {}, json={})


# ── 未登入 ────────────────────────────────────────────────

@pytest.mark.parametrize('method,path,allowed', ADMIN_ROUTES, ids=_IDS)
def test_requires_authentication(client, method, path, allowed):
    """沒有 token 一律 401。"""
    resp = _call(client, method, path)
    assert resp.status_code == 401, (
        f'{method} {path} 未登入卻回 {resp.status_code}'
    )


# ── 玩家自助 token（本檔案的核心）──────────────────────────

@pytest.mark.parametrize('method,path,allowed', ADMIN_ROUTES, ids=_IDS)
def test_player_token_cannot_reach_admin_api(client, player_headers, method, path, allowed):
    """玩家自助 token 一律 403 —— 不管它要求的是讀還是寫。

    這是整個檔案最重要的斷言。玩家 token 的簽章是合法的，所以
    @jwt_required() 會放它過；擋住它的必須是 admin_api() / require_role()。
    """
    resp = _call(client, method, path, player_headers)
    assert resp.status_code == 403, (
        f'{method} {path} 讓玩家自助 token 通過了（回 {resp.status_code}）'
        ' —— 這支路由應該掛 admin_api()'
    )


# ── viewer（只能讀，不能寫）────────────────────────────────

@pytest.mark.parametrize(
    'method,path',
    [(m, p) for m, p, allowed in ADMIN_ROUTES if allowed == WRITE_ROLES],
    ids=[f'{m} {p}' for m, p, a in ADMIN_ROUTES if a == WRITE_ROLES],
)
def test_viewer_cannot_write(client, viewer_headers, method, path):
    """viewer 角色不能碰任何寫入路由。"""
    resp = _call(client, method, path, viewer_headers)
    assert resp.status_code == 403, (
        f'{method} {path} 讓 viewer 寫入了（回 {resp.status_code}）'
    )


@pytest.mark.parametrize(
    'method,path',
    [(m, p) for m, p, allowed in ADMIN_ROUTES if allowed == READ_ROLES],
    ids=[f'{m} {p}' for m, p, a in ADMIN_ROUTES if a == READ_ROLES],
)
def test_viewer_can_read(client, viewer_headers, method, path):
    """viewer 讀得到唯讀路由（可能 404，但不能是 401/403）。"""
    resp = _call(client, method, path, viewer_headers)
    assert resp.status_code not in (401, 403), (
        f'{method} {path} 把有讀取權的 viewer 擋掉了（回 {resp.status_code}）'
    )


# ── operator（讀寫都可以）─────────────────────────────────

@pytest.mark.parametrize('method,path,allowed', ADMIN_ROUTES, ids=_IDS)
def test_operator_is_not_blocked(client, operator_headers, method, path, allowed):
    """operator 不該被權限層擋掉。

    404（找不到那筆資料）、400（body 是空的）都算通過 —— 這裡只在意
    有沒有被 401/403 擋下來。
    """
    resp = _call(client, method, path, operator_headers)
    assert resp.status_code not in (401, 403), (
        f'{method} {path} 把 operator 擋掉了（回 {resp.status_code}）'
    )


# ═══════════════════════════════════════════════════════════
#  防止「新增路由忘記掛權限」
# ═══════════════════════════════════════════════════════════

# 這些藍圖底下的路由**刻意**不需要後台角色。新增例外時請在這裡註明原因，
# 這樣 code review 時會看到「又多了一個公開端點」。
UNGUARDED_ALLOWLIST = {
    # ── 公開端點（不需要 token）──────────────────────────────
    'auth.login',                       # 後台登入本身
    'app_player.register_player',       # 公開自助註冊
    'app_player.login_player',          # 公開自助登入
    'app_admin.index',                  # 後台 SPA 的 HTML 殼（靜態檔）

    # ── 自己驗證 refresh token，不需要角色 ───────────────────
    'auth.refresh',
    'app_player.refresh_player',

    # ── 自我範圍：只回傳呼叫者自己的身分 ─────────────────────
    'auth.me',

    # ── 玩家自助區塊：由 @player_required 保護，只能動自己的資料 ──
    # （這些其實有保護，只是關鍵字在 player_required 而不是 admin_api，
    #   上面的原始碼比對抓得到，所以正常不會出現在這裡。列著當文件。）

    # ── 推播 token 註冊：綁在 JWT identity 上，非後台資料 ──────
    # ⚠️ unregister 目前沒有比對 username（見審查報告 E8），
    #    知道別人的 device token 就能刪掉它。已知問題，非高風險。
    'app_device.register_device',
    'app_device.unregister_device',

    # ── 遊戲參考資料（唯讀）─────────────────────────────────
    # 來源是公開的 Star Citizen Wiki / UEX API，不是公會私有資料。
    # /item/search 是玩家端 MyPlayerView.vue 的物品自動完成在用，
    # 所以這一組必須對玩家 token 開放。
    # （相對地 /item/sync* 是後台設定頁專用，已收成 admin_api。）
    'app_item.list_items',
    'app_item.search_items',
    'app_item.list_types',
    'app_item.get_item',
    'app_item.get_item_prices',
    'app_item.list_vehicles',
    'app_item.list_commodities',
    # 製造藍圖主檔（同樣是公開遊戲資料，玩家端的藍圖自動完成要用）
    'app_blueprint.list_master',
    'app_blueprint.search_master',
    'app_blueprint.master_output_types',
    'app_blueprint.master_for_item',
    'app_blueprint.get_master',
    # 礦物回波參考表（同樣是公開遊戲資料，來源是 scunpacked-data；
    # 純查詢對照表，沒有寫入動作，後台/玩家兩種身分都應該看得到）
    'app_mining.list_deposits',
    'app_mining.list_locations',
    'app_mining.list_systems',
    # 「誰有這張藍圖」—— 比照 app_inventory.where_item，公會成員互查是功能需求
    'app_blueprint.blueprint_holders',

    # ── 玩家端 UI 需要的庫存唯讀查詢 ─────────────────────────
    'app_inventory.list_locations',
    'app_inventory.where_item',   # 刻意公開：「公會裡誰有這個東西」是功能需求
    'app_inventory.search_stock', # 同上，只是改成一個關鍵字同時搜物品／地點／玩家
    'app_inventory.list_stock',   # 玩家 token 會被 _owner_from_args 強制綁回自己
    'app_inventory.capacity',     # 同上
}

# 完全公開、不需要任何 token 的藍圖
PUBLIC_BLUEPRINTS = {
    'app_docs',   # 說明頁
    'sample',     # 腳手架殘留的範例路由（建議移除，見審查報告 E8）
    'flasgger',   # Swagger UI（⚠️ 目前對外公開，見審查報告 A8）
    'static',
    'status',     # GET / healthcheck
    None,
}


def test_no_admin_route_is_left_unguarded(app):
    """走過 Flask 的 url_map，找出沒有權限保護的後台路由。

    這支測試的目的不是驗證行為，而是讓「新增後台路由但忘記掛 admin_api()」
    這件事在 CI 就被抓到，而不是等到有人發現玩家能刪別人的資料。
    """
    import inspect

    suspects = []
    for rule in app.url_map.iter_rules():
        endpoint = rule.endpoint
        blueprint = endpoint.rsplit('.', 1)[0] if '.' in endpoint else None

        if blueprint in PUBLIC_BLUEPRINTS or endpoint in UNGUARDED_ALLOWLIST:
            continue
        # 只看會改變狀態或吐資料的方法
        methods = rule.methods - {'HEAD', 'OPTIONS'}
        if not methods:
            continue

        view = app.view_functions[endpoint]
        # admin_api() / require_role() / player_required 都會把檢查包進 closure，
        # 用原始碼比對最直接：抓得到裝飾器名稱就算有保護。
        try:
            source = inspect.getsource(view.__wrapped__ if hasattr(view, '__wrapped__') else view)
        except (OSError, TypeError):
            source = ''

        guarded = any(token in source for token in
                      ('admin_api', 'require_role', 'player_required'))
        if not guarded:
            suspects.append(f'{sorted(methods)} {rule.rule} → {endpoint}')

    assert not suspects, (
        '以下路由沒有掛 admin_api() / require_role() / player_required：\n  '
        + '\n  '.join(suspects)
        + '\n\n若確定它應該公開，請加進 tests/test_permissions.py 的 '
          'UNGUARDED_ALLOWLIST 並註明原因。'
    )


# ═══════════════════════════════════════════════════════════
#  資料破壞：部分更新不得清空關鍵欄位
# ═══════════════════════════════════════════════════════════

def test_partial_update_does_not_wipe_other_fields(client, auth_headers):
    """`PUT /player/<id>` 只帶 notes 時，不能把其他欄位清成空字串。

    舊版 `_serialize_form` 無條件回傳全部 6 個 key、缺的填 ''，而
    `Player.update` 只擋 None 不擋 ''，所以送 {"notes": "x"} 會把
    star_citizen_id 清空 —— 該玩家從此無法登入，個人庫存變成孤兒，
    而且沒有任何還原路徑。
    """
    created = client.post('/player/', headers=auth_headers, json={
        'player_name': 'Alice',
        'star_citizen_id': 'AliceSC',
        'nickname': 'Ali',
        'discord_name': 'ali#0001',
        'notes': '原本的備註',
    })
    assert created.status_code == 201, created.get_json()
    player_id = created.get_json()['id']

    resp = client.put(f'/player/{player_id}', headers=auth_headers,
                      json={'notes': '只改備註'})
    assert resp.status_code == 200, resp.get_json()

    after = client.get(f'/player/{player_id}', headers=auth_headers).get_json()['data']
    assert after['notes'] == '只改備註'
    # 沒傳的欄位必須原封不動
    assert after['star_citizen_id'] == 'AliceSC', 'star_citizen_id 被清空了'
    assert after['player_name'] == 'Alice',       'player_name 被清空了'
    assert after['nickname'] == 'Ali',            'nickname 被清空了'
    assert after['discord_name'] == 'ali#0001',   'discord_name 被清空了'


def test_cannot_blank_star_citizen_id(client, auth_headers):
    """明確送空字串也要被擋（400），不能靜默寫進資料庫。"""
    created = client.post('/player/', headers=auth_headers, json={
        'player_name': 'Bob', 'star_citizen_id': 'BobSC',
    })
    player_id = created.get_json()['id']

    resp = client.put(f'/player/{player_id}', headers=auth_headers,
                      json={'star_citizen_id': ''})
    assert resp.status_code == 400

    after = client.get(f'/player/{player_id}', headers=auth_headers).get_json()['data']
    assert after['star_citizen_id'] == 'BobSC'


def test_blueprint_partial_update_keeps_name_and_status(client, auth_headers):
    """藍圖也是同一個 bug：只改 notes 不能把 name 清空、unlock_status 重設。"""
    created = client.post('/blueprint/', headers=auth_headers, json={
        'name': 'Ballista 藍圖', 'unlock_status': 'unlocked', 'notes': '舊備註',
    })
    assert created.status_code == 201, created.get_json()
    bp_id = created.get_json()['id']

    resp = client.put(f'/blueprint/{bp_id}', headers=auth_headers,
                      json={'notes': '新備註'})
    assert resp.status_code == 200, resp.get_json()

    after = client.get(f'/blueprint/{bp_id}', headers=auth_headers).get_json()['data']
    assert after['notes'] == '新備註'
    assert after['name'] == 'Ballista 藍圖', 'name 被清空了'
    assert after['unlock_status'] == 'unlocked', 'unlock_status 被重設回 obtained 了'


# ═══════════════════════════════════════════════════════════
#  資料外洩：玩家 token 不能查別人的個人庫
# ═══════════════════════════════════════════════════════════

def test_player_token_inventory_query_is_scoped_to_self(client, player_headers):
    """玩家帶 ?owner_type=player&player=<別人> 時，必須被綁回自己身上。"""
    resp = client.get('/inventory/?owner_type=player&player=SomeoneElse',
                      headers=player_headers)
    # 這支路由對玩家 token 開放（前端有用到），但範圍必須被強制改寫
    assert resp.status_code == 200, resp.get_json()

    resp2 = client.get('/inventory/capacity?owner_type=player&player=SomeoneElse',
                       headers=player_headers)
    assert resp2.status_code == 200
    assert resp2.get_json()['player'] == 'TestPilot', (
        '玩家 token 查到了別人的個人庫容量'
    )


# ═══════════════════════════════════════════════════════════
#  更改密碼：玩家自助（需驗證目前密碼）與後台重設（不需要）
# ═══════════════════════════════════════════════════════════

def test_player_can_change_own_password(client):
    """驗證目前密碼正確後，新密碼立刻生效、舊密碼立刻失效。"""
    reg = client.post('/player/register', json={
        'nickname': 'PwChanger', 'star_citizen_id': 'PwChanger', 'password': 'old-pw-123',
    })
    assert reg.status_code == 201, reg.get_json()
    login = client.post('/player/login', json={
        'star_citizen_id': 'PwChanger', 'password': 'old-pw-123',
    })
    assert login.status_code == 200, login.get_json()
    headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

    resp = client.put('/player/me/password', headers=headers, json={
        'current_password': 'old-pw-123', 'new_password': 'new-pw-456',
    })
    assert resp.status_code == 200, resp.get_json()

    relogin = client.post('/player/login', json={
        'star_citizen_id': 'PwChanger', 'password': 'new-pw-456',
    })
    assert relogin.status_code == 200, '新密碼登入失敗'

    stale = client.post('/player/login', json={
        'star_citizen_id': 'PwChanger', 'password': 'old-pw-123',
    })
    assert stale.status_code == 401, '舊密碼理應失效，卻還能登入'


def test_player_password_change_rejects_wrong_current_password(client):
    """目前密碼打錯就該被擋下來，而且密碼不能被悄悄改掉。"""
    client.post('/player/register', json={
        'nickname': 'PwGuard', 'star_citizen_id': 'PwGuard', 'password': 'right-pw-1',
    })
    login = client.post('/player/login', json={
        'star_citizen_id': 'PwGuard', 'password': 'right-pw-1',
    })
    headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

    resp = client.put('/player/me/password', headers=headers, json={
        'current_password': 'wrong-pw', 'new_password': 'new-pw-999',
    })
    assert resp.status_code == 400, resp.get_json()

    still_old = client.post('/player/login', json={
        'star_citizen_id': 'PwGuard', 'password': 'right-pw-1',
    })
    assert still_old.status_code == 200, '密碼在驗證失敗的情況下被改掉了'


def test_player_password_change_enforces_min_length(client, player_headers):
    resp = client.put('/player/me/password', headers=player_headers, json={
        'current_password': 'player-pw-123', 'new_password': '123',
    })
    assert resp.status_code == 400


def test_admin_can_reset_player_password(client, auth_headers):
    """後台重設密碼不需要舊密碼 —— 也涵蓋『後台建的玩家從沒設過密碼』這種情況。"""
    created = client.post('/player/', headers=auth_headers, json={
        'player_name': 'ResetMe', 'star_citizen_id': 'ResetMeSC',
    })
    assert created.status_code == 201, created.get_json()
    player_id = created.get_json()['id']

    # 後台建立的玩家沒有密碼欄位，重設之前完全無法登入
    before = client.post('/player/login', json={
        'star_citizen_id': 'ResetMeSC', 'password': 'anything',
    })
    assert before.status_code == 401

    resp = client.put(f'/player/{player_id}/password', headers=auth_headers, json={
        'new_password': 'admin-set-pw-1',
    })
    assert resp.status_code == 200, resp.get_json()

    login = client.post('/player/login', json={
        'star_citizen_id': 'ResetMeSC', 'password': 'admin-set-pw-1',
    })
    assert login.status_code == 200, '後台設定的密碼無法登入'


def test_admin_password_reset_enforces_min_length(client, auth_headers):
    created = client.post('/player/', headers=auth_headers, json={
        'player_name': 'Short', 'star_citizen_id': 'ShortPwSC',
    })
    player_id = created.get_json()['id']

    resp = client.put(f'/player/{player_id}/password', headers=auth_headers,
                      json={'new_password': '123'})
    assert resp.status_code == 400


def test_admin_password_reset_404_for_missing_player(client, auth_headers):
    resp = client.put(f'/player/{_OID}/password', headers=auth_headers,
                      json={'new_password': 'longenough1'})
    assert resp.status_code == 404
