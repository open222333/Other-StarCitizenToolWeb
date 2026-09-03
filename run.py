import json
import secrets
from os import environ
from os.path import join, exists

# 本機開發：自動載入 .env（Docker 不影響，docker-compose 已透過 env_file 注入）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_FLASK_JSON_PATH = join('conf', 'flask.json')
if not exists(_FLASK_JSON_PATH):
    with open(_FLASK_JSON_PATH, 'w') as _f:
        json.dump({}, _f)
with open(_FLASK_JSON_PATH, 'r') as _f:
    _flask_conf = json.load(_f)

if not _flask_conf.get('SECRET_KEY'):
    _flask_conf['SECRET_KEY'] = secrets.token_hex(32)
    with open(_FLASK_JSON_PATH, 'w') as _f:
        json.dump(_flask_conf, _f, indent=2)
    print('[init] 已自動產生 SECRET_KEY 並寫入 conf/flask.json')

from app import create_app
from conf.config import TestingConfig
from src.models.user import User
from src.models.user_template import UserTemplate
from src.mongo import ensure_indexes
from src import FLASK_PORT, MYSQL_PASSWORD, REDIS_PASSWORD
from src.secret_guard import collect_weak_secrets, format_startup_error

# ── fail-closed：機密值還是範本值就拒絕啟動 ──
# .env.default 與 conf/config.ini.default 都是公開在版控裡的範本，所以
# 「ADMIN_PASSWORD=admin」等於後台沒有密碼（任何人打一次
# POST /auth/login {"username":"admin","password":"admin"} 就取得 admin token）、
# 「REDIS_PASSWORD=redis_password」等於 Rate Limiting 與 Celery broker
# 對主機上任何人開放。判斷邏輯在 src/secret_guard.py（那邊有測試）。
#
# 這段刻意放在連資料庫之前，讓設定錯誤在第一秒就失敗。
# MYSQL_PASSWORD 用 required=False：本專案沒有任何程式用到 MySQL，
# 留空是正常狀態；但一旦填了就不接受範本值。
_admin_password = environ.get('ADMIN_PASSWORD', '')
_problems = collect_weak_secrets([
    ('ADMIN_PASSWORD', _admin_password, True),
    ('REDIS_PASSWORD', REDIS_PASSWORD, True),
    ('MYSQL_PASSWORD', MYSQL_PASSWORD, False),
])
if _problems:
    raise SystemExit(format_startup_error(_problems))

app = create_app(config_object=TestingConfig)
ensure_indexes()

# ── 確保系統預設「管理者」使用者模板存在 ──
admin_tmpl_id = UserTemplate.ensure_defaults()

# ── 確保預設 admin 帳號存在（密碼強度已在檔頭驗證過）──
admin = User.find_by_username('admin')
if not admin:
    User.create('admin', _admin_password, role='admin', template_id=admin_tmpl_id)
    print('[init] 已建立預設帳號 admin，密碼已從 ADMIN_PASSWORD 環境變數設定')
else:
    # 修正舊資料：確保 role 與 template_id 正確
    needs_update = {}
    if not admin.get('role'):
        needs_update['role'] = 'admin'
    if not admin.get('template_id'):
        needs_update['template_id'] = admin_tmpl_id
    if needs_update:
        User.update(
            str(admin['_id']),
            role=needs_update.get('role'),
            template_id=needs_update.get('template_id', admin.get('template_id')),
        )
        print(f'[init] 已修正 admin 帳號資料：{list(needs_update.keys())}')

if __name__ == "__main__":
    _debug = environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=_debug)
