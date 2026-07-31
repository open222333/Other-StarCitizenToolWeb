from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity,
)
from src.models.user import User
from src.models.user_template import UserTemplate
from src.models.log import Log
from src.limiter import limiter

app_auth = Blueprint('auth', __name__)


@app_auth.route('/login', methods=['POST'])
@limiter.limit('10 per minute')
def login():
    """
    帳號密碼登入，回傳 JWT token
    ---
    tags:
      - Auth
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [username, password]
          properties:
            username:    {type: string,  example: admin}
            password:    {type: string,  example: admin}
            remember_me: {type: boolean, description: "true = 同時回傳 30 天 refresh_token"}
    responses:
      200:
        description: 登入成功
        schema:
          properties:
            success:       {type: boolean}
            token:         {type: string, description: "Access token（8 小時）"}
            refresh_token: {type: string, description: "Refresh token（30 天，remember_me=true 時才回傳）"}
            role:          {type: string}
            template_id:   {type: string}
      401:
        description: 帳號或密碼錯誤
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '缺少請求參數'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'success': False, 'message': 'username 或 password 不得為空'}), 400

    user = User.find_by_username(username)
    if not user or not User.check_password(password, user['password']):
        Log.create(username or 'unknown', 'login', '帳號或密碼錯誤', success=False)
        return jsonify({'success': False, 'message': '帳號或密碼錯誤'}), 401

    template_id = user.get('template_id')
    resp = {
        'success':     True,
        'token':       create_access_token(identity=username),
        'role':        user.get('role', 'viewer'),
        'template_id': str(template_id) if template_id else None,
    }
    if data.get('remember_me'):
        resp['refresh_token'] = create_refresh_token(identity=username)

    Log.create(username, 'login', '登入成功', success=True)
    return jsonify(resp)


@app_auth.route('/refresh', methods=['POST'])
@limiter.limit('30 per minute')
@jwt_required(refresh=True)
def refresh():
    """
    用 Refresh Token 換發新的 Access Token
    ---
    tags:
      - Auth
    security:
      - Bearer: []
    description: >
      Authorization header 帶 Refresh Token（格式同 Bearer），
      成功後回傳新的 access token。
    responses:
      200:
        description: 換發成功
        schema:
          properties:
            success: {type: boolean}
            token:   {type: string}
            role:    {type: string}
      401:
        description: Refresh token 無效或過期
    """
    username = get_jwt_identity()
    user = User.find_by_username(username)
    if not user:
        return jsonify({'success': False, 'message': '使用者不存在'}), 401
    return jsonify({
        'success': True,
        'token':   create_access_token(identity=username),
        'role':    user.get('role', 'viewer'),
    })


@app_auth.route('/me', methods=['GET'])
@jwt_required()
def me():
    """
    驗證 token 並回傳目前使用者資訊
    ---
    tags:
      - Auth
    security:
      - Bearer: []
    responses:
      200:
        description: Token 有效
        schema:
          properties:
            success:       {type: boolean}
            username:      {type: string}
            role:          {type: string}
            template_id:   {type: string}
            template_name: {type: string}
            is_protected:  {type: boolean, description: "true = 系統保護帳號（admin），不可刪除"}
      401:
        description: Token 無效或過期
    """
    username = get_jwt_identity()
    user = User.find_by_username(username)
    if not user:
        return jsonify({'success': False, 'message': '使用者不存在'}), 401

    template_id   = user.get('template_id')
    template_name = None

    if template_id:
        tmpl = UserTemplate.find_by_id(str(template_id))
        if tmpl:
            template_name = tmpl.get('name')

    return jsonify({
        'success':       True,
        'username':      username,
        'role':          user.get('role', 'viewer'),
        'template_id':   str(template_id) if template_id else None,
        'template_name': template_name,
        'is_protected':  username == 'admin',
    })
