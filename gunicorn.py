# ============================================================
# gunicorn.py — Gunicorn 啟動設定檔
#
# 啟動方式：
#   gunicorn -c gunicorn.py "run:app"
#
# 所有參數均可在 conf/config.ini [GUNICORN] 區塊覆寫。
# ============================================================
from configparser import ConfigParser
from os import cpu_count, environ
from os.path import join

_cfg = ConfigParser()
_cfg.read(join('conf', 'config.ini'))


def _s(key, fallback):
    return _cfg.get('GUNICORN', key, fallback=str(fallback))

def _i(key, fallback):
    return int(_s(key, fallback))

def _b(key, fallback):
    return _s(key, str(fallback)).lower() in ('true', '1', 'yes')


# ── Bind ──────────────────────────────────────────────────────
_host = _s('HOST', '0.0.0.0')
_port = _s('PORT', environ.get('FLASK_PORT', '5000'))
bind  = f'{_host}:{_port}'

# ── Workers ───────────────────────────────────────────────────
workers      = _i('WORKERS',      (cpu_count() or 1) * 2 + 1)
worker_class = _s('WORKER_CLASS', 'sync')
threads      = _i('THREADS',      1)
timeout      = _i('TIMEOUT',      120)
keepalive    = _i('KEEPALIVE',    5)

# Docker 建議設為 /dev/shm（RAM disk），本機留空使用系統預設
_wtd         = _s('WORKER_TMP_DIR', '')
worker_tmp_dir = _wtd if _wtd else None

# ── Logging ───────────────────────────────────────────────────
accesslog = _s('ACCESS_LOG', '-')    # - 代表 stdout
errorlog  = _s('ERROR_LOG',  '-')    # - 代表 stderr
loglevel  = _s('LOG_LEVEL',  'info')

# ── Misc ──────────────────────────────────────────────────────
preload_app = _b('PRELOAD_APP', True)   # fork 前預先載入 app，節省記憶體
reload      = _b('RELOAD',     False)  # 僅開發環境設為 true
