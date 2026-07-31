from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.models.device_token import DeviceToken, PLATFORMS

app_device = Blueprint('app_device', __name__)


@app_device.route('/register', methods=['POST'])
@jwt_required()
def register_device():
    """登記裝置推播 token。
    ---
    parameters:
      - in: body
        schema:
          required: [token, platform]
          properties:
            token:       {type: string, description: "FCM token 或 APNs device token"}
            platform:    {type: string, enum: [ios, android, web]}
            app_version: {type: string}
    responses:
      200:
        description: 登記成功
    """
    data = request.get_json() or {}
    token       = (data.get('token') or '').strip()
    platform    = (data.get('platform') or '').strip().lower()
    app_version = (data.get('app_version') or '').strip()

    if not token:
        return jsonify({'success': False, 'message': 'token 不得為空'}), 400
    if platform not in PLATFORMS:
        return jsonify({'success': False, 'message': f'platform 須為 {", ".join(PLATFORMS)} 之一'}), 400

    username = get_jwt_identity()
    DeviceToken.register(username, token, platform, app_version)
    return jsonify({'success': True})


@app_device.route('/unregister', methods=['POST'])
@jwt_required()
def unregister_device():
    """移除裝置推播 token（登出時呼叫）。
    ---
    parameters:
      - in: body
        schema:
          required: [token]
          properties:
            token: {type: string}
    responses:
      200:
        description: 移除成功
    """
    data  = request.get_json() or {}
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'success': False, 'message': 'token 不得為空'}), 400

    DeviceToken.unregister(token)
    return jsonify({'success': True})
