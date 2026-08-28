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
from src import FLASK_PORT

# ── fail-closed：ADMIN_PASSWORD 沒設或還是範本值就拒絕啟動 ──
# .env.default 是公開的，所以「ADMIN_PASSWORD=admin」等於後台沒有密碼 ——
# 任何人打一次 POST /auth/login {"username":"admin","password":"admin"} 就取得
# admin token，可讀寫全部使用者、玩家名冊、庫存與稽核日誌。
# 這段刻意放在連資料庫之前，讓設定錯誤在第一秒就失敗。
_admin_password = environ.get('ADMIN_PASSWORD', '')
_WEAK_ADMIN_PASSWORDS = {'', 'admin', 'password', 'changeme', '123456'}
if _admin_password.strip().lower() in _WEAK_ADMIN_PASSWORDS:
    raise SystemExit(
        '[init] 拒絕啟動：環境變數 ADMIN_PASSWORD 未設定或使用了預設／弱密碼。\n'
        '        請在 .env 設定一組強密碼後再啟動，例如用這行產生：\n'
        "        python3 -c \"import secrets,string;a=string.ascii_letters+string.digits;"
        "print(''.join(secrets.choice(a) for _ in range(24)))\""
    )

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
