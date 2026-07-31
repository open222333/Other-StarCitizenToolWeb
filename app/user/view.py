from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.models.user import User, ROLES, _UNSET
from src.models.user_template import UserTemplate
from src.permissions import require_role

app_user = Blueprint('app_user', __name__)


# ═══════════════════════════════════════════
#  使用者管理
# ═══════════════════════════════════════════

@app_user.route('/', methods=['GET'])
@jwt_required()
@require_role('admin')
def list_users():
    """列出所有使用者（不含密碼）"""
    return jsonify({'success': True, 'data': User.find_all()})


@app_user.route('/', methods=['POST'])
@jwt_required()
@require_role('admin')
def create_user():
    """新增使用者（角色由模板決定）"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '缺少請求參數'}), 400

    username    = data.get('username', '').strip()
    password    = data.get('password', '')
    template_id = data.get('template_id', '') or None

    if not username or not password:
        return jsonify({'success': False, 'message': 'username 或 password 不得為空'}), 400

    if len(username) < 3 or len(username) > 50:
        return jsonify({'success': False, 'message': 'username 長度須介於 3～50 字元'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'message': 'password 長度不得少於 6 字元'}), 400

    if not template_id:
        return jsonify({'success': False, 'message': '請指定使用者模板（template_id）'}), 400

    # 從模板取得角色
    tmpl = UserTemplate.find_by_id(template_id)
    if not tmpl:
        return jsonify({'success': False, 'message': '使用者模板不存在'}), 404
    role = tmpl.get('role', 'viewer')

    if User.find_by_username(username):
        return jsonify({'success': False, 'message': '使用者已存在'}), 409

    user_id = User.create(username, password, role=role, template_id=template_id)
    return jsonify({'success': True, 'id': user_id}), 201


@app_user.route('/<user_id>', methods=['PUT'])
@jwt_required()
@require_role('admin')
def update_user(user_id):
    """修改使用者（密碼或模板）；切換模板時自動同步角色"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '缺少請求參數'}), 400

    password = data.get('password') or None
    role     = None  # 角色由模板決定，不接受直接設定

    # template_id: 有傳入（含空字串）才處理，不傳入則跳過
    if 'template_id' in data:
        template_id = data['template_id'] or None   # '' → None（清除模板）
    else:
        template_id = _UNSET

    # 若指定了新模板，同步角色
    if template_id is not _UNSET and template_id:
        tmpl = UserTemplate.find_by_id(str(template_id))
        if not tmpl:
            return jsonify({'success': False, 'message': '使用者模板不存在'}), 404
        role = tmpl.get('role')

    if not password and template_id is _UNSET:
        return jsonify({'success': False, 'message': '請提供 password 或 template_id'}), 400

    if not User.update(user_id, password=password, role=role, template_id=template_id):
        return jsonify({'success': False, 'message': '使用者不存在'}), 404

    return jsonify({'success': True})


@app_user.route('/<user_id>', methods=['DELETE'])
@jwt_required()
@require_role('admin')
def delete_user(user_id):
    """刪除使用者（不可刪除自己；admin 為系統保護帳號不可刪除）"""
    current = get_jwt_identity()
    current_user = User.find_by_username(current)
    if current_user and str(current_user['_id']) == user_id:
        return jsonify({'success': False, 'message': '無法刪除自己的帳號'}), 400

    result = User.delete(user_id)
    if result == 'protected':
        return jsonify({'success': False, 'message': 'admin 為系統保護帳號，不可刪除'}), 403
    if result == 'not_found':
        return jsonify({'success': False, 'message': '使用者不存在'}), 404

    return jsonify({'success': True})


# ═══════════════════════════════════════════
#  使用者模板 CRUD
# ═══════════════════════════════════════════

@app_user.route('/templates/', methods=['GET'])
@jwt_required()
@require_role('admin')
def list_templates():
    """列出所有使用者模板"""
    return jsonify({'success': True, 'data': UserTemplate.find_all()})


@app_user.route('/templates/', methods=['POST'])
@jwt_required()
@require_role('admin')
def create_template():
    """新增使用者模板"""
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': '模板名稱不得為空'}), 400
    if len(name) > 100:
        return jsonify({'success': False, 'message': '模板名稱長度不得超過 100 字元'}), 400

    role = data.get('role', 'viewer')
    if role not in ROLES:
        return jsonify({'success': False, 'message': f'無效的角色，可用值：{", ".join(ROLES)}'}), 400

    tid = UserTemplate.create(
        name=name,
        role=role,
        description=data.get('description', ''),
    )
    return jsonify({'success': True, 'id': tid}), 201


@app_user.route('/templates/<tid>', methods=['PUT'])
@jwt_required()
@require_role('admin')
def update_template(tid):
    """更新使用者模板；若角色有變更，自動同步所有指派此模板的使用者"""
    data = request.get_json(silent=True) or {}
    name        = data.get('name')
    description = data.get('description')
    role        = data.get('role')

    if name is not None:
        name = name.strip()
        if not name:
            return jsonify({'success': False, 'message': '模板名稱不得為空'}), 400
        if len(name) > 100:
            return jsonify({'success': False, 'message': '模板名稱長度不得超過 100 字元'}), 400

    if role is not None and role not in ROLES:
        return jsonify({'success': False, 'message': f'無效的角色，可用值：{", ".join(ROLES)}'}), 400

    if not UserTemplate.update(tid, name=name, description=description, role=role):
        return jsonify({'success': False, 'message': '模板不存在'}), 404

    # 角色有變更 → 同步所有持有此模板的使用者
    if role is not None:
        updated = User.update_role_by_template(tid, role)
        return jsonify({'success': True, 'synced_users': updated})

    return jsonify({'success': True})


@app_user.route('/templates/<tid>', methods=['DELETE'])
@jwt_required()
@require_role('admin')
def delete_template(tid):
    """刪除使用者模板（系統預設模板不可刪除）"""
    result = UserTemplate.delete(tid)
    if result == 'system':
        return jsonify({'success': False, 'message': '系統預設模板不可刪除'}), 403
    if result == 'not_found':
        return jsonify({'success': False, 'message': '模板不存在'}), 404
    return jsonify({'success': True})
