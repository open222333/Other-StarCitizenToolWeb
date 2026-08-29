"""後台 API 的角色控管。

⚠️ 為什麼 `@jwt_required()` 單獨用是不夠的：

本專案有兩套身分體系 —— 後台帳號（app/auth/view.py，identity = username）與玩家
自助帳號（app/player/view.py，identity = `player:<scid>`，額外帶 claim `is_player=True`）。
兩者**共用同一把 JWT 金鑰**（conf/config.py 把 SECRET_KEY 同時指派給 JWT_SECRET_KEY），
而 `@jwt_required()` 只驗簽章 —— 它不看 identity 格式，也不看自訂 claim。

所以玩家自助 token 可以直接通過任何只掛 `@jwt_required()` 的後台路由。
後台路由一律要用本模組的 `admin_api()`（或 `@jwt_required()` + `@require_role()`）。
"""

from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from src.models.user import User

# 標記「這是玩家自助 token」的 claim 名稱。定義在這裡（而不是 app/player/view.py）
# 是為了避免循環 import —— app 藍圖本來就都 import 這個模組。
#
# ⚠️ 不可以叫 'type'：那是 flask-jwt-extended 的保留 claim（access / refresh），
#    蓋掉它會讓 refresh token 跟 access token 無法區分。詳見 app/player/view.py。
PLAYER_CLAIM = 'is_player'

ROLE_LEVELS = {'admin': 3, 'operator': 2, 'viewer': 1}

# 後台路由的兩組標準角色，避免各藍圖各自寫一份字串 tuple
READ_ROLES = ('admin', 'operator', 'viewer')
WRITE_ROLES = ('admin', 'operator')


def _player_token_rejection():
    """玩家自助 token 一律不得進入後台 API。回傳 response tuple 或 None。"""
    if get_jwt().get(PLAYER_CLAIM):
        return jsonify({'success': False, 'message': '此 token 不是後台帳號'}), 403
    return None


def require_role(*roles):
    """限制只有指定角色可以存取，同時拒絕玩家自助 token。

    必須搭配 `@jwt_required()`（放在本裝飾器上方）使用，否則 get_jwt() 會失敗。
    新程式碼建議直接用 `admin_api()`，它把兩者包在一起。
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            rejected = _player_token_rejection()
            if rejected:
                return rejected

            username = get_jwt_identity()
            user = User.find_by_username(username)
            if not user or user.get('role') not in roles:
                return jsonify({'success': False, 'message': '權限不足'}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def admin_api(*roles):
    """後台 API 專用：等同 `@jwt_required()` + `@require_role(*roles)`。

    把兩個裝飾器合成一個，是為了讓「忘記加角色檢查」這件事不可能發生 ——
    新增後台路由時只會想到要不要 `admin_api`，而不是「要不要在 jwt_required
    下面再補一個 require_role」。

    用法：
        @app_x.route('/', methods=['GET'])
        @admin_api(*READ_ROLES)
        def list_x(): ...
    """
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        @require_role(*roles)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapper
    return decorator
