import json
import logging
from os import environ
from flask import Flask, request, jsonify
from flask_cors import CORS
from flasgger import Swagger
from flask_jwt_extended import JWTManager
from werkzeug.exceptions import HTTPException
from app.sample.view import app_sample
from app.auth.view import app_auth
from app.user.view import app_user
from app.admin.view import app_admin
from app.log.view import app_log
from app.docs.view import app_docs
from app.device.view import app_device
from src import FLASK_JSON_PATH
from src.limiter import limiter

app = Flask(__name__)
template = {
    "swagger": "2.0",
    # "openapi": "3.0.0",
    "info": {
        "title": "My API",
        "description": "練習用 API文檔",
        "contact": {
            "responsibleOrganization": "ME",
            "responsibleDeveloper": "Me",
            "email": "open222333@gmail.com",
            "url": "www.test.com",
        },
        "termsOfService": "http://test.com/terms",
        "version": "0.0.1"
    },
    "host": "127.0.0.1",  # overrides localhost:500
    "basePath": "/",  # base bash for blueprint registration
    "schemes": [
        "http",
        # "https"
    ],
    "operationId": "getmyData",
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT token，格式: Bearer <token>"
        }
    }
}

swagger = Swagger(app, template=template)
jwt = JWTManager(app)
limiter.init_app(app)

# CORS origins：
#   - Vite 開發伺服器固定允許
#   - 生產域名從 CORS_ORIGIN 環境變數讀取（可多個，逗號分隔）
_extra = [o.strip() for o in environ.get('CORS_ORIGIN', '').split(',') if o.strip()]
_origins = ['http://localhost:5173'] + _extra
CORS(app, origins=_origins, supports_credentials=True)


@app.route("/")
def status():
    return 'ok'


@app.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response


@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return jsonify({'success': False, 'message': e.description}), e.code
    logging.exception('Unhandled error on %s %s: %s', request.method, request.path, e)
    return jsonify({'success': False, 'message': '伺服器內部錯誤'}), 500


def create_app(config_object=None):
    app.register_blueprint(blueprint=app_sample, url_prefix='/sample')
    app.register_blueprint(blueprint=app_auth, url_prefix='/auth')
    app.register_blueprint(blueprint=app_user, url_prefix='/user')
    app.register_blueprint(blueprint=app_admin, url_prefix='/admin')
    app.register_blueprint(blueprint=app_log, url_prefix='/log')
    app.register_blueprint(blueprint=app_device, url_prefix='/device')
    app.register_blueprint(blueprint=app_docs, url_prefix='/docs')
    if config_object:
        app.config.from_object(config_object)
    return app
