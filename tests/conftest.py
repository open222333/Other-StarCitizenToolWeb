"""
測試設定與全域 fixture。

MongoDB / Redis 在測試中使用記憶體 mock，不需要任何外部服務。
執行方式：
    pip install -r requirements-test.txt
    pytest              # 執行全部測試
    pytest -v -s        # 詳細輸出
    pytest tests/test_auth.py   # 單一檔案
"""
import os

os.environ.setdefault('TESTING', '1')

# ── 在 Flask app 載入前，替換所有外部依賴 ─────────────────────────

import mongomock
import fakeredis
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# 1. MongoDB → mongomock（記憶體模式，不需要真實連線）
import src.mongo as _mongo_mod

_MONGO_CLIENT = mongomock.MongoClient()
_MONGO_DB = _MONGO_CLIENT['flask_app_test']
_mongo_mod.get_db = lambda: _MONGO_DB

# 2. Redis → fakeredis（記憶體模式）
import src.redis_client as _redis_mod

_FAKE_REDIS = fakeredis.FakeRedis(decode_responses=True)
_redis_mod.get_redis = lambda: _FAKE_REDIS

# 3. Flask-Limiter → 記憶體 storage（避免連線真實 Redis）
#    在 app/__init__.py 的 `from src.limiter import limiter` 之前替換，
#    後續所有藍圖的 @limiter.limit(...) 裝飾器都會拿到這個記憶體版本。
import src.limiter as _limiter_mod

_limiter_mod.limiter = Limiter(
    key_func=get_remote_address,
    storage_uri='memory://',
    default_limits=[],
    enabled=False,
)

# ─────────────────────────────────────────────────────────────────

import pytest


@pytest.fixture(scope='session')
def app():
    """建立 Flask test app（整個 session 共用一個實例）。"""
    from app import create_app
    flask_app = create_app()
    flask_app.config.update({
        'TESTING': True,
        'RATELIMIT_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'JWT_SECRET_KEY': 'test-jwt-secret-key',
    })
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_db():
    """每個測試結束後清空全部 collection，保持測試隔離。"""
    yield
    for name in _MONGO_DB.list_collection_names():
        _MONGO_DB.drop_collection(name)


@pytest.fixture(autouse=True)
def clean_redis():
    """每個測試結束後清空 Redis。"""
    yield
    _FAKE_REDIS.flushall()


@pytest.fixture
def seed_admin():
    """建立系統 admin 帳號，回傳 (username, password)。"""
    from src.models.user_template import UserTemplate
    from src.models.user import User
    tid = UserTemplate.ensure_defaults()
    User.create('admin', 'Admin1234!', role='admin', template_id=tid)
    return 'admin', 'Admin1234!'


@pytest.fixture
def admin_token(client, seed_admin):
    """取得 admin JWT access token。"""
    username, password = seed_admin
    resp = client.post('/auth/login', json={
        'username': username,
        'password': password,
    })
    return resp.get_json()['token']


@pytest.fixture
def auth_headers(admin_token):
    """包含 Bearer token 的 Authorization header dict。"""
    return {'Authorization': f'Bearer {admin_token}'}
