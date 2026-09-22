"""玩家名冊 API。

- 一般 CRUD（列表／新增／編輯／刪除）：後台用，需要登入（比照 app/user/view.py）。
- `POST /player/register`：公開自助註冊，不需要登入，只收暱稱＋遊戲ID。

`star_citizen_id` 就是 src/models/inventory.py 個人庫用的 `player`（RSI handle）
字串，兩邊共用同一個值，不建立額外的外鍵對應。
"""

from flask import Blueprint, g, jsonify, request
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    get_jwt, get_jwt_identity, jwt_required,
)

from src import WMS_SCOPE_ID
from src.limiter import limiter
from src.models.blueprint import (ACQUISITION_METHODS, DEFAULT_UNLOCK_STATUS,
                                  UNLOCK_STATUSES, Blueprint as BlueprintModel)
from src.models.inventory import OWNER_PLAYER, Inventory, InventoryLog, StockError
from src.models.item import BlueprintMaster, ItemMaster
from src.models.log import Log
from src.models.player import Player, PlayerError
from src.permissions import PLAYER_CLAIM, READ_ROLES, WRITE_ROLES, admin_api
from app._shared import attach_item_names

app_player = Blueprint('app_player', __name__)


@app_player.errorhandler(StockError)
def handle_stock_error(err):
    """StockError 是預期中的使用者錯誤（例如庫存不足、找不到物品），訊息直接回給玩家看。"""
    return jsonify({'success': False, 'message': str(err)}), 400

PLAYER_IDENTITY_PREFIX = 'player:'

# 標記「這是玩家自助 token」的 claim 名稱。
#
# ⚠️ 千萬不要用 'type' —— 那是 flask-jwt-extended 自己的保留 claim，它用
#    type='access' / type='refresh' 來區分兩種 token。之前這裡傳
#    additional_claims={'type': 'player'} 把它蓋掉了，造成兩個問題：
#      1. /player/refresh 永遠回 422「Only refresh tokens are allowed」，
#         玩家 8 小時後一律被登出，refresh 功能等於不存在。
#      2. 更糟：access 與 refresh token 的 type 都變成 'player'，而
#         verify_token_type() 對非 refresh 端點只擋 type == 'refresh'。
#         於是**30 天有效的 refresh token 可以直接當 access token 用**，
#         短效 access token 的意義完全消失。



def _player_identity(star_citizen_id: str) -> str:
    """玩家 JWT 的 identity 字串，跟後台 users 的 identity（username 本身）區隔開，
    避免玩家 token 被誤用來打需要 admin/operator/viewer role 的後台 API。"""
    return f'{PLAYER_IDENTITY_PREFIX}{star_citizen_id}'


def _scid_from_identity():
    """玩家 token 的 star_citizen_id；不是玩家 token 就回 None。"""
    identity = get_jwt_identity() or ''
    if not identity.startswith(PLAYER_IDENTITY_PREFIX):
        return None
    return identity[len(PLAYER_IDENTITY_PREFIX):] or None


def player_required(fn):
    """比照 jwt_required()，但額外檢查這個 token 是玩家自己的
    （additional_claims.type == 'player'），而且那個帳號現在還存在。

    為什麼要多查一次 DB：JWT 一旦簽出去就無法撤銷，access token 8 小時、
    refresh token 30 天。只看 claim 的話，管理員把某個玩家軟刪除之後，
    那個人在 token 到期前照樣能讀寫自己的個人庫存，「移除成員」等於沒有效果。

    這件事之前只有 /player/me 與 /player/blueprints 做到（它們本來就要撈
    player doc），四支個人庫存端點沒做 —— 同一個檔案裡兩套標準。集中在這裡
    做，之後新增端點就不會再漏。

    代價是每個請求多一次 players 的 indexed find_one（star_citizen_id 有
    unique index），對這個規模的公會工具可以忽略。
    """
    from functools import wraps

    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        if not get_jwt().get(PLAYER_CLAIM):
            return jsonify({'success': False, 'message': '此 token 不是玩家帳號'}), 403

        scid = _scid_from_identity()
        player = Player.find_by_star_citizen_id(scid) if scid else None
        if not player:
            return jsonify({'success': False, 'message': '這個帳號已不存在，請重新登入'}), 403

        # 存進 request context 讓 _self_player_doc() 直接取用，
        # 否則需要 player doc 的端點會在同一個請求裡查第二次。
        g.player_doc = player
        return fn(*args, **kwargs)
    return wrapper


_FORM_FIELDS = ('player_name', 'star_citizen_id', 'nickname',
                'discord_name', 'discord_id', 'notes')

# 這兩個欄位被清空的後果不可逆：star_citizen_id 是玩家登入的帳號、也是
# inventory.player 的 join key，清空後玩家再也無法登入、個人庫變成孤兒，
# 而且 unique index 不是 partial，第二個被清空的玩家會直接撞 DuplicateKeyError。
_NEVER_EMPTY = ('player_name', 'star_citizen_id')


def _serialize_form(data: dict, *, partial: bool = False) -> dict:
    """整理表單欄位。

    `partial=True`（PUT 用）只回傳 data 裡實際出現的 key —— 否則沒傳的欄位會被
    當成空字串寫進資料庫。舊版無條件回傳全部 6 個 key、缺的填 ''，所以
    `PUT /player/<id> {"notes": "x"}` 會把該玩家的 player_name、star_citizen_id、
    nickname、discord_* 全部清空。
    """
    if partial:
        return {k: (data.get(k) or '').strip() for k in _FORM_FIELDS if k in data}
    return {k: (data.get(k) or '').strip() for k in _FORM_FIELDS}


# ═══════════════════════════════════════════
#  後台 CRUD（需後台帳號 + 角色）
#
#  這一段是「可以操作任何玩家」的管理端，跟下面玩家自助的區塊
#  （@player_required，只能動自己）是完全不同的信任等級。
#  一律用 admin_api()，不要只掛 @jwt_required() —— 玩家自助 token
#  會直接通過 @jwt_required()，詳見 src/permissions.py 的說明。
# ═══════════════════════════════════════════

@app_player.route('/', methods=['GET'])
@admin_api(*READ_ROLES)
def list_players():
    """列出所有玩家。

    `?include_deleted=1` 會一併回傳已軟刪除的玩家（回傳的文件帶 `deleted_at`）。
    後台需要看得到他們才能還原 —— 否則誤刪的成員在畫面上等於消失，
    而他的遊戲ID在自助註冊時又會出現「已經被註冊過了」，沒有人能解釋。
    """
    include_deleted = request.args.get('include_deleted') in ('1', 'true', 'True')
    return jsonify({'success': True,
                    'data': Player.find_all(include_deleted=include_deleted)})


@app_player.route('/<player_id>', methods=['GET'])
@admin_api(*READ_ROLES)
def get_player(player_id):
    """單一玩家資料。"""
    player = Player.find_by_id(player_id)
    if not player:
        return jsonify({'success': False, 'message': '找不到玩家'}), 404
    return jsonify({'success': True, 'data': player})


@app_player.route('/', methods=['POST'])
@admin_api(*WRITE_ROLES)
def create_player():
    """新增玩家（後台用，欄位比自助註冊完整）。"""
    data = request.get_json(silent=True) or {}
    fields = _serialize_form(data)

    if not fields['player_name']:
        return jsonify({'success': False, 'message': '玩家名稱不得為空'}), 400
    if not fields['star_citizen_id']:
        return jsonify({'success': False, 'message': 'Star Citizen ID 不得為空'}), 400

    try:
        player_id = Player.create(**fields)
    except PlayerError as e:
        return jsonify({'success': False, 'message': str(e)}), 409

    return jsonify({'success': True, 'id': player_id}), 201


@app_player.route('/<player_id>', methods=['PUT'])
@admin_api(*WRITE_ROLES)
def update_player(player_id):
    """更新玩家資料（只更新有傳入的欄位）。"""
    data = request.get_json(silent=True) or {}
    fields = _serialize_form(data, partial=True)

    if not fields:
        return jsonify({'success': False, 'message': '沒有要更新的欄位'}), 400
    for key in _NEVER_EMPTY:
        if key in fields and not fields[key]:
            return jsonify({'success': False, 'message': f'{key} 不得為空'}), 400

    try:
        ok = Player.update(player_id, **fields)
    except PlayerError as e:
        return jsonify({'success': False, 'message': str(e)}), 409

    if not ok:
        return jsonify({'success': False, 'message': '玩家不存在或沒有變更'}), 404
    return jsonify({'success': True})


@app_player.route('/<player_id>', methods=['DELETE'])
@admin_api(*WRITE_ROLES)
def delete_player(player_id):
    """軟刪除玩家（開發原則：重要資料不做永久刪除）。可用 /restore 還原。"""
    player = Player.find_by_id(player_id)
    if not Player.soft_delete(player_id):
        return jsonify({'success': False, 'message': '玩家不存在'}), 404

    Log.create(get_jwt_identity(), 'delete_player',
               f'移除玩家：{(player or {}).get("player_name")}'
               f'（{(player or {}).get("star_citizen_id")}）', success=True)
    return jsonify({'success': True})


@app_player.route('/<player_id>/restore', methods=['POST'])
@admin_api(*WRITE_ROLES)
def restore_player(player_id):
    """還原被軟刪除的玩家。

    個人庫存與藍圖是用 star_citizen_id 字串對應的，所以還原之後原本的資料
    會自動回到他名下，不需要另外搬。
    ---
    tags: [Player]
    security:
      - Bearer: []
    responses:
      200:
        description: 已還原
      404:
        description: 找不到這筆已移除的玩家
      409:
        description: 這個遊戲ID已經有一筆使用中的玩家資料
    """
    player = Player.find_by_id(player_id, include_deleted=True)

    try:
        ok = Player.restore(player_id)
    except PlayerError as e:
        return jsonify({'success': False, 'message': str(e)}), 409

    if not ok:
        return jsonify({'success': False, 'message': '找不到這筆已移除的玩家'}), 404

    Log.create(get_jwt_identity(), 'restore_player',
               f'還原玩家：{(player or {}).get("player_name")}'
               f'（{(player or {}).get("star_citizen_id")}）', success=True)
    return jsonify({'success': True})


@app_player.route('/<player_id>/password', methods=['PUT'])
@admin_api(*WRITE_ROLES)
def set_player_password(player_id):
    """後台直接設定／重設某玩家的登入密碼，不需要知道原密碼。

    獨立成一支路由，不跟 update_player() 共用 _serialize_form()：那條路徑是
    「字串欄位原樣寫進 DB」，密碼要先 bcrypt hash 過，混在一起容易漏做雜湊
    或誤把明碼存進 DB。也順便涵蓋「玩家是後台 create_player() 建立、從來
    沒設過密碼」的情況 —— 那種玩家在這支路由跑之前完全無法登入。
    ---
    tags: [Player]
    security:
      - Bearer: []
    parameters:
      - in: body
        schema:
          required: [new_password]
          properties:
            new_password: {type: string, description: "至少 6 個字元"}
    responses:
      200:
        description: 成功
      400:
        description: 密碼太短
      404:
        description: 玩家不存在
    """
    player = Player.find_by_id(player_id)
    if not player:
        return jsonify({'success': False, 'message': '找不到玩家'}), 404

    data = request.get_json(silent=True) or {}
    new_password = data.get('new_password') or ''
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '新密碼至少需要 6 個字元'}), 400

    Player.set_password(player['_id'], new_password)

    username = get_jwt_identity()
    Log.create(username, 'reset_player_password',
               f'重設玩家密碼：{player.get("player_name")}（{player.get("star_citizen_id")}）',
               success=True)
    return jsonify({'success': True})


# ═══════════════════════════════════════════
#  公開自助註冊（不需要登入）
# ═══════════════════════════════════════════

@app_player.route('/register', methods=['POST'])
@limiter.limit('10 per minute')
def register_player():
    """玩家自助註冊：暱稱、遊戲ID（唯一）、密碼。註冊完成即可用 /player/login 登入。"""
    data = request.get_json(silent=True) or {}
    nickname        = (data.get('nickname') or '').strip()
    star_citizen_id = (data.get('star_citizen_id') or '').strip()
    password        = data.get('password') or ''
    # 相容前端目前的 payload（player_name 目前跟 nickname 相同值）
    player_name = (data.get('player_name') or nickname or '').strip()

    if not nickname:
        return jsonify({'success': False, 'message': '暱稱不得為空'}), 400
    if not star_citizen_id:
        return jsonify({'success': False, 'message': '遊戲ID 不得為空'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'message': '密碼至少需要 6 個字元'}), 400

    if Player.find_by_star_citizen_id(star_citizen_id):
        return jsonify({'success': False, 'message': '這個遊戲ID已經被註冊過了'}), 409

    try:
        player_id = Player.create(
            player_name=player_name or nickname,
            star_citizen_id=star_citizen_id,
            nickname=nickname,
            password=password,
        )
    except PlayerError as e:
        return jsonify({'success': False, 'message': str(e)}), 409

    return jsonify({'success': True, 'id': player_id}), 201


@app_player.route('/login', methods=['POST'])
@limiter.limit('10 per minute')
def login_player():
    """玩家登入：用遊戲ID（star_citizen_id）＋密碼，回傳玩家專用 JWT。

    這組 token 跟後台 `/auth/login` 發出的 admin/operator/viewer token 是分開的
    身分體系（additional_claims.type == 'player'），玩家 token 不能拿去打
    後台需要 role 的 API，反之亦然。
    """
    data = request.get_json(silent=True) or {}
    star_citizen_id = (data.get('star_citizen_id') or '').strip()
    password        = data.get('password') or ''

    if not star_citizen_id or not password:
        return jsonify({'success': False, 'message': '遊戲ID 或密碼不得為空'}), 400

    player = Player.find_by_star_citizen_id(star_citizen_id, include_password=True)
    if not player or not Player.check_password(password, player.get('password')):
        return jsonify({'success': False, 'message': '遊戲ID 或密碼錯誤'}), 401

    identity = _player_identity(star_citizen_id)
    claims = {PLAYER_CLAIM: True}
    resp = {
        'success':         True,
        'token':           create_access_token(identity=identity, additional_claims=claims),
        'refresh_token':   create_refresh_token(identity=identity, additional_claims=claims),
        'nickname':        player.get('nickname'),
        'star_citizen_id': player.get('star_citizen_id'),
    }
    return jsonify(resp)


@app_player.route('/refresh', methods=['POST'])
@limiter.limit('30 per minute')
@jwt_required(refresh=True)
def refresh_player():
    """用玩家 refresh token 換發新的 access token（比照 /auth/refresh）。"""
    identity = get_jwt_identity()
    if not identity.startswith(PLAYER_IDENTITY_PREFIX):
        return jsonify({'success': False, 'message': '此 refresh token 不是玩家帳號'}), 403

    # refresh token 有 30 天，這裡不查 DB 的話，被移除的玩家可以一路換發新的
    # access token 到 refresh token 過期為止 —— 等於「移除成員」要一個月後才生效。
    scid = _scid_from_identity()
    if not scid or not Player.find_by_star_citizen_id(scid):
        return jsonify({'success': False, 'message': '這個帳號已不存在，請重新登入'}), 403

    return jsonify({
        'success': True,
        'token':   create_access_token(identity=identity, additional_claims={PLAYER_CLAIM: True}),
    })


@app_player.route('/search', methods=['GET'])
@player_required
def search_players():
    """依暱稱／遊戲ID／真實名稱找玩家，給「查詢」頁的「玩家id」「玩家暱稱」
    兩個自動完成欄位用——使用者打字看候選名單，選一個代入查詢欄位。

    掛 @player_required 而不是這個檔案其他唯讀端點慣用的 admin_api()：
    這支本來就要給任何登入玩家用（比照 /inventory/search、/blueprint/holders
    這類公會成員互查功能），跟這個檔案裡其他 CRUD 端點的信任等級不同，見
    檔案開頭那段「一律用 admin_api()」的說明——那是給後台專屬端點的規則，
    這支跟 /player/me、/player/blueprints 一樣是玩家自助區塊。

    故意不回 Discord 欄位，見 Player.search_basic() 的說明。
    ---
    tags: [Player]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: q, type: string, required: true, description: "暱稱／遊戲ID／真實名稱"}
      - {in: query, name: limit, type: integer, default: 20, description: "最多 50"}
    responses:
      200:
        description: 成功（q 是空字串時回空陣列，不是錯誤）
    """
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({'success': True, 'data': []})
    try:
        limit = int(request.args.get('limit', 20))
    except ValueError:
        limit = 20
    rows = Player.search_basic(q, limit=limit)
    return jsonify({'success': True, 'data': rows})


@app_player.route('/me', methods=['GET'])
@player_required
def get_current_player():
    """玩家自己查詢自己的名冊資料（用玩家 token，不是後台 token）。"""
    star_citizen_id = get_jwt_identity()[len(PLAYER_IDENTITY_PREFIX):]
    player = Player.find_by_star_citizen_id(star_citizen_id)
    if not player:
        return jsonify({'success': False, 'message': '找不到玩家'}), 404
    return jsonify({'success': True, 'data': player})


@app_player.route('/me', methods=['PUT'])
@player_required
def update_current_player():
    """玩家自己修改自己的資料。

    只能改暱稱／Discord／備註 —— `star_citizen_id`（遊戲ID）刻意不開放自己改，
    因為它同時是 inventory.player / discord_bindings.handle 用的鍵值，
    改了會讓既有的個人庫存對不起來。要換遊戲ID要請管理員從後台處理。
    ---
    tags: [Player]
    security:
      - Bearer: []
    parameters:
      - in: body
        schema:
          properties:
            nickname:       {type: string}
            discord_name:   {type: string}
            discord_id:     {type: string}
            discord_public: {type: boolean, description: "是否讓其他玩家在查詢結果看到自己的 Discord。預設 false"}
            notes:          {type: string}
    responses:
      200:
        description: 成功
      404:
        description: 找不到玩家
    """
    star_citizen_id = get_jwt_identity()[len(PLAYER_IDENTITY_PREFIX):]
    player = Player.find_by_star_citizen_id(star_citizen_id)
    if not player:
        return jsonify({'success': False, 'message': '找不到玩家'}), 404

    data = request.get_json(silent=True) or {}
    fields = {}
    for key in ('nickname', 'discord_name', 'discord_id', 'notes'):
        if key in data:
            fields[key] = (data.get(key) or '').strip()

    # 布林欄位不能走上面那圈 —— (False or '').strip() 會變成空字串 ''，
    # 存進 DB 後 bool('') 剛好還是 False，看起來沒事，但 True 會變成 'True'
    # 這種字串，之後 bool('False') 之類的比對就全錯了。
    if 'discord_public' in data:
        fields['discord_public'] = bool(data.get('discord_public'))

    if not fields:
        return jsonify({'success': True})

    Player.update(player['_id'], **fields)
    return jsonify({'success': True})


@app_player.route('/me/discord-code', methods=['POST'])
@player_required
@limiter.limit('5 per minute')
def issue_my_discord_code():
    """產生一組 10 分鐘有效的 Discord 綁定碼，拿去 Discord 打 `/bind`。

    Discord 帳號與遊戲帳號之間沒有可信連結，所以「證明你是這個遊戲ID的人」
    這件事只能在需要密碼的地方做 —— 也就是這裡。詳見
    src/models/inventory.py 的 DiscordBinding.bind()。
    ---
    tags: [Player]
    security:
      - Bearer: []
    responses:
      200:
        description: 回傳 code 與 expires_at
      404:
        description: 找不到玩家
    """
    player = _self_player_doc()
    issued = Player.issue_discord_code(player['_id'])
    if not issued:
        return jsonify({'success': False, 'message': '找不到玩家資料，請重新登入'}), 404

    # 綁定碼本身不寫進稽核日誌（等同一次性密碼），只記「有產生」這件事
    Log.create(f'player:{player.get("star_citizen_id")}', 'issue_discord_code',
               f'產生 Discord 綁定碼：{player.get("star_citizen_id")}', success=True)
    return jsonify({'success': True,
                    'code': issued['code'],
                    'expires_at': issued['expires_at'].isoformat() + 'Z',
                    'star_citizen_id': player.get('star_citizen_id')})


@app_player.route('/me/password', methods=['PUT'])
@player_required
@limiter.limit('10 per minute')
def change_my_password():
    """玩家自己更改登入密碼，需先驗證目前密碼。

    跟後台的 set_player_password() 不同：這裡是本人操作，沒有 role 當作
    背書，所以一定要先核對 current_password 才能改，避免一個沒鎖螢幕的
    分頁或外流的 access token 被拿來直接把密碼換掉、永久鎖死本人。
    ---
    tags: [Player]
    security:
      - Bearer: []
    parameters:
      - in: body
        schema:
          required: [current_password, new_password]
          properties:
            current_password: {type: string}
            new_password:      {type: string, description: "至少 6 個字元"}
    responses:
      200:
        description: 成功
      400:
        description: 目前密碼錯誤，或新密碼太短
    """
    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password') or ''
    new_password     = data.get('new_password') or ''

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '新密碼至少需要 6 個字元'}), 400

    # g.player_doc（player_required 存的）用的是預設的 find_by_star_citizen_id()，
    # 沒帶 include_password=True，password 欄位在 _serialize() 就被拿掉了 ——
    # 這裡要驗證目前密碼，得帶 include_password=True 重查一次。
    scid = _self_star_citizen_id()
    player = Player.find_by_star_citizen_id(scid, include_password=True)
    if not player or not Player.check_password(current_password, player.get('password')):
        return jsonify({'success': False, 'message': '目前密碼不正確'}), 400

    Player.set_password(player['_id'], new_password)
    return jsonify({'success': True})


# ═══════════════════════════════════════════
#  玩家自助個人庫（需玩家登入，只能動自己的個人庫）
#  跟 app/inventory/view.py 共用 src/models/inventory.py 的邏輯，
#  差別只在這裡強制 owner_type=player 且 player 一律是呼叫者自己，
#  不像後台 /inventory/add 需要 admin/operator role。
# ═══════════════════════════════════════════

def _self_star_citizen_id() -> str:
    return get_jwt_identity()[len(PLAYER_IDENTITY_PREFIX):]


def _resolve_item_or_400(value: str) -> dict:
    value = (value or '').strip()
    if not value:
        raise StockError('必須指定物品。')
    item = ItemMaster.resolve(value)
    if not item:
        raise StockError(f'找不到物品「{value}」，或對到多筆。請改用 uuid（見 /item/search）。')
    return item


def _positive_int(data: dict, field: str) -> int:
    raw = data.get(field)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise StockError(f'{field} 必須是整數。')
    if value <= 0:
        raise StockError(f'{field} 必須大於 0。')
    if value > 1_000_000:
        raise StockError(f'{field} 超過單次上限 1,000,000。')
    return value


@app_player.route('/inventory', methods=['GET'])
@player_required
def list_my_inventory():
    """我的個人庫存清單（只有自己的，不會看到別人的）。
    ---
    tags: [Player]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    scid = _self_star_citizen_id()
    rows, total = Inventory.list_stock(WMS_SCOPE_ID, OWNER_PLAYER, scid, limit=200)
    summary = Inventory.capacity(WMS_SCOPE_ID, OWNER_PLAYER, scid)
    return jsonify({'success': True, 'data': rows, 'total': total, 'summary': summary})


@app_player.route('/inventory/add', methods=['POST'])
@player_required
def add_my_inventory():
    """把自己擁有的物品登記進個人庫（選擇物品＋數量＋地點）。
    ---
    tags: [Player]
    security:
      - Bearer: []
    parameters:
      - in: body
        schema:
          required: [item, quantity, location]
          properties:
            item:      {type: string, description: "遊戲 uuid 或完整名稱"}
            quantity:  {type: integer}
            location:  {type: string}
            container: {type: string}
            note:      {type: string}
    responses:
      200:
        description: 成功
      400:
        description: 參數錯誤
    """
    scid = _self_star_citizen_id()
    data = request.get_json(silent=True) or {}
    item = _resolve_item_or_400(data.get('item'))
    quantity = _positive_int(data, 'quantity')
    location = (data.get('location') or '').strip()
    if not location:
        raise StockError('必須指定地點。')

    doc = Inventory.adjust(
        WMS_SCOPE_ID, OWNER_PLAYER, scid,
        location=location, container=data.get('container'),
        item_id=item['_id'], delta=quantity,
        actor=_player_identity(scid), actor_id=f'player:{scid}',
        note=(data.get('note') or '').strip(),
    )

    return jsonify({'success': True, 'data': {
        'item_id': item['_id'], 'item_name': item['name'],
        'quantity': doc['quantity'], 'delta': quantity,
        'location': doc['location'], 'container': doc.get('container'),
    }})


@app_player.route('/inventory/remove', methods=['POST'])
@player_required
def remove_my_inventory():
    """從自己的個人庫取出物品（可以附備註，記錄為何取出）。
    ---
    tags: [Player]
    security:
      - Bearer: []
    parameters:
      - in: body
        schema:
          required: [item, quantity, location]
          properties:
            item:      {type: string}
            quantity:  {type: integer}
            location:  {type: string}
            container: {type: string}
            note:      {type: string, description: "為何取出，選填"}
    responses:
      200:
        description: 成功
      400:
        description: 庫存不足或參數錯誤
    """
    scid = _self_star_citizen_id()
    data = request.get_json(silent=True) or {}
    item = _resolve_item_or_400(data.get('item'))
    quantity = _positive_int(data, 'quantity')
    location = (data.get('location') or '').strip()
    if not location:
        raise StockError('必須指定地點。')

    doc = Inventory.adjust(
        WMS_SCOPE_ID, OWNER_PLAYER, scid,
        location=location, container=data.get('container'),
        item_id=item['_id'], delta=-quantity,
        actor=_player_identity(scid), actor_id=f'player:{scid}',
        note=(data.get('note') or '').strip(),
    )

    return jsonify({'success': True, 'data': {
        'item_id': item['_id'], 'item_name': item['name'],
        'quantity': doc['quantity'], 'delta': -quantity,
        'location': doc['location'], 'container': doc.get('container'),
    }})


@app_player.route('/inventory/history', methods=['GET'])
@player_required
def my_inventory_history():
    """我的個人庫存入／取出紀錄。
    ---
    tags: [Player]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: limit, type: integer, default: 50, description: "最多 200"}
    responses:
      200:
        description: 成功
    """
    scid = _self_star_citizen_id()
    try:
        limit = int(request.args.get('limit', 50))
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 200))

    rows = InventoryLog.recent_for_owner(WMS_SCOPE_ID, OWNER_PLAYER, scid, limit=limit)

    # 補上物品名稱／中文名稱，前端不用再逐筆查（單一 $in 批次查，見 app/_shared.py）
    return jsonify({'success': True, 'data': attach_item_names(rows)})


# ═══════════════════════════════════════════
#  玩家自助藍圖名冊（需玩家登入，只能動自己的藍圖）
#  跟 app/blueprint/view.py 共用 src/models/blueprint.py，差別是這裡
#  player_id 一律強制是呼叫者自己，不用 player_id 參數讓玩家亂填。
# ═══════════════════════════════════════════

def _self_player_doc() -> dict:
    """目前登入玩家自己的名冊資料（含 _id）。

    player_required 已經查過並放進 g.player_doc，這裡直接取用，不重查。
    g 沒有值代表這支端點沒掛 player_required（不該發生），退回自己查一次。
    """
    player = getattr(g, 'player_doc', None)
    if player:
        return player
    player = Player.find_by_star_citizen_id(_self_star_citizen_id())
    if not player:
        raise StockError('找不到玩家資料，請重新登入。')
    return player


@app_player.route('/blueprints', methods=['GET'])
@player_required
def list_my_blueprints():
    """我擁有的藍圖清單。
    ---
    tags: [Player]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    player = _self_player_doc()
    # limit 要蓋過 find_all 的預設 500：那個上限是為了「列出全部玩家的藍圖」
    # 才存在的，套到「單一玩家自己的清單」上會出事 —— 遊戲主檔有 1,600+ 張，
    # 登記超過 500 張的玩家會拿到被截斷的清單，而批量登記頁靠這支端點判斷
    # 「哪些已登記」，於是已登記的圖會顯示成可勾選（畫面說謊）。
    rows = BlueprintModel.find_all(player_id=player['_id'],
                                   limit=BlueprintModel.PLAYER_MAX)

    # 有連到主檔的補上遊戲資料（產出物、製作時間、材料數）。
    # 一次 $in 批次查，不要逐筆 find_one —— 玩家可能登記幾十張藍圖。
    uuids = [r['blueprint_uuid'] for r in rows if r.get('blueprint_uuid')]
    masters = {}
    if uuids:
        for doc in BlueprintMaster._col().find(
                {'_id': {'$in': uuids}}, BlueprintMaster.PROJECTION):
            masters[doc['_id']] = doc

    for row in rows:
        master = masters.get(row.get('blueprint_uuid'))
        row['master'] = {
            'name': master.get('name'),
            'name_zh': master.get('name_zh'),
            'output_type': master.get('output_type'),
            'output_type_label': master.get('output_type_label'),
            'craft_time_label': master.get('craft_time_label'),
            'ingredient_count': master.get('ingredient_count'),
            'is_current': master.get('is_current'),
        } if master else None

    return jsonify({
        'success': True,
        'data': rows,
        'acquisition_methods': ACQUISITION_METHODS,
        'unlock_statuses': UNLOCK_STATUSES,
    })


@app_player.route('/blueprints', methods=['POST'])
@player_required
def add_my_blueprint():
    """登記自己擁有／解鎖的一張藍圖。
    ---
    tags: [Player]
    security:
      - Bearer: []
    parameters:
      - in: body
        schema:
          required: [blueprint_uuid]
          properties:
            blueprint_uuid:         {type: string, description: "藍圖主檔 uuid，從 /blueprint/master/search 選出來的。必填"}
            notes:                  {type: string}
            acquisition_method:     {type: string}
            acquisition_location:   {type: string}
    responses:
      200:
        description: 成功
      400:
        description: 參數錯誤（沒帶 blueprint_uuid，或該 uuid 不在主檔裡）
    """
    player = _self_player_doc()
    data = request.get_json(silent=True) or {}
    blueprint_uuid = (data.get('blueprint_uuid') or '').strip()

    # 玩家端**只能**登記主檔裡存在的藍圖，不接受自由輸入的名稱。
    #
    # 為什麼要這樣限制：同一張藍圖如果每個人自己打字，就會出現
    # 「Omnisky III」「omnisky 3」「奧姆尼斯基3」好幾種寫法，
    # 「誰有這張圖」（/blueprint/holders）就分不成同一組，整個查詢功能失效。
    #
    # ⚠️ 這讓藍圖主檔變成硬依賴 —— 主檔沒同步過的話玩家什麼都登記不了。
    #    前端會在主檔為空時顯示提示，而不是給一個永遠搜不到東西的輸入框。
    #    後台（app/blueprint/view.py）仍可自由輸入，當作例外處理的逃生門。
    if not blueprint_uuid:
        raise StockError('請從清單中選擇藍圖（不接受自行輸入名稱）。')

    master = BlueprintMaster.get(blueprint_uuid)
    if not master:
        raise StockError('找不到這張藍圖，請重新從清單選擇。')

    # 名稱一律以主檔為準，不看 client 傳什麼
    name = master.get('name') or ''
    if not name:
        raise StockError('這張藍圖在主檔裡沒有名稱，請聯絡管理員。')

    blueprint_id = BlueprintModel.create(
        name=name,
        player_id=player['_id'],
        acquisition_method=(data.get('acquisition_method') or '').strip(),
        acquisition_location=(data.get('acquisition_location') or '').strip(),
        # 狀態刻意**不看** client 傳什麼，一律寫死。
        #
        # 玩家端「登記」的語意就是「我有這張圖」，所以沒有其他狀態可選 ——
        # 前端也已經不顯示狀態欄位。但只做在前端等於沒做：直接打 API 帶
        # {"unlock_status": "locked"} 就能讓自己從「誰有這張藍圖」的結果裡
        # 消失（HOLDER_HIDDEN_STATUSES 會濾掉 locked），或帶 "unlocked"
        # 誤導別人來問。要改狀態一律走後台 PUT /blueprint/<id>。
        unlock_status=DEFAULT_UNLOCK_STATUS,
        notes=(data.get('notes') or '').strip(),
        blueprint_uuid=blueprint_uuid,
    )
    return jsonify({'success': True, 'id': blueprint_id}), 201


#: 一次批量登記的上限。
#
#  1,600+ 張主檔全勾起來送出並不是合理操作（畫面一頁最多 200 筆），
#  而沒有上限的話一個請求就能塞爆 insert_many 與回應大小。
MAX_BULK_BLUEPRINTS = 200


@app_player.route('/blueprints/bulk', methods=['POST'])
@player_required
@limiter.limit('20 per minute')
def add_my_blueprints_bulk():
    """一次登記多張藍圖（畫面上勾選後送出）。

    跟單筆登記同樣的規則：只能登記主檔裡存在的 uuid、名稱一律取自主檔、
    狀態一律寫死。已經登記過的會被**跳過**而不是新增第二筆 —— 回應會分別
    列出實際新增與跳過的數量，讓畫面能誠實說「新增 12 張、跳過 3 張」。
    ---
    tags: [Player]
    security:
      - Bearer: []
    parameters:
      - in: body
        schema:
          required: [blueprint_uuids]
          properties:
            blueprint_uuids:      {type: array, items: {type: string}, description: "主檔 uuid 清單，最多 200 筆"}
            acquisition_method:   {type: string}
            acquisition_location: {type: string}
            notes:                {type: string}
    responses:
      200:
        description: 成功（含 added / skipped / not_found 統計）
      400:
        description: 沒有帶 uuid、或超過單次上限
    """
    player = _self_player_doc()
    data = request.get_json(silent=True) or {}
    raw = data.get('blueprint_uuids')
    if not isinstance(raw, list) or not raw:
        raise StockError('請先勾選要登記的藍圖。')

    # ⚠️ 先看**原始長度**再做任何逐項處理。
    #
    # 舊版是「去重後才檢查上限」，所以 `['bp-1'] * 1500000` 這種 body
    # （12MB，還在 MAX_CONTENT_LENGTH 16MB 之內）會先跑完 150 萬次
    # str()/strip() 與一次 dict.fromkeys 才被擋下 —— 實測單一請求峰值
    # 多吃 114MB 記憶體、耗時 1 秒，而限速是 20 次/分鐘，一個帳號就能
    # 讓 gunicorn worker 反覆配置 GB 級記憶體。
    if len(raw) > MAX_BULK_BLUEPRINTS:
        raise StockError(f'一次最多只能登記 {MAX_BULK_BLUEPRINTS} 張，'
                         f'這次送出了 {len(raw)} 筆。')

    # uuid 是 36 字元的 GUID，給到 64 已經很寬鬆。不設上限的話 200 筆
    # 超長字串會組出超過 Mongo 16MB 命令上限的 $in 查詢 → DocumentTooLarge
    # → 未攔截的 500（StockError 之外的例外都是 500）。
    uuids = [u for u in (str(item).strip() for item in raw)
             if u and len(u) <= 64]
    # 去重後才算「實際要處理幾筆」，跟畫面上的「已選 N 張」一致
    uuids = list(dict.fromkeys(uuids))

    # 一次 $in 批次查主檔，順便拿到名稱（不接受 client 傳來的名稱）
    names = BlueprintMaster.names_by_ids(uuids)
    items = [{'uuid': uuid, 'name': (names.get(uuid) or {}).get('name') or ''}
             for uuid in uuids if (names.get(uuid) or {}).get('name')]
    not_found = [uuid for uuid in uuids
                 if not (names.get(uuid) or {}).get('name')]

    result = BlueprintModel.bulk_create_for_player(
        player['_id'], items,
        acquisition_method=(data.get('acquisition_method') or '').strip(),
        acquisition_location=(data.get('acquisition_location') or '').strip(),
        notes=(data.get('notes') or '').strip(),
    )

    Log.create(f'player:{player.get("star_citizen_id")}', 'bulk_add_blueprints',
               f'批量登記藍圖：新增 {len(result["added"])} 張、'
               f'跳過 {len(result["skipped"])} 張、'
               f'主檔查不到 {len(not_found)} 張', success=True)

    return jsonify({
        'success': True,
        'added': len(result['added']),
        'skipped': len(result['skipped']),
        'not_found': len(not_found),
        'added_uuids': result['added'],
    })


@app_player.route('/blueprints/<blueprint_id>', methods=['DELETE'])
@player_required
def delete_my_blueprint(blueprint_id):
    """刪除自己名下的一筆藍圖紀錄（只能刪自己的，其他人的即使猜到 id 也刪不掉）。
    ---
    tags: [Player]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
      404:
        description: 找不到（或不是自己的）
    """
    player = _self_player_doc()
    if not BlueprintModel.soft_delete(blueprint_id, player_id=player['_id']):
        return jsonify({'success': False, 'message': '找不到這筆藍圖紀錄'}), 404
    return jsonify({'success': True})
