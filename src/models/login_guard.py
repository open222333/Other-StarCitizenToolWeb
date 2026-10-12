"""登入防暴力破解（後台 /auth/login 與玩家 /player/login 共用）。

除了 Flask-Limiter 的每 IP 次數限制（src/limiter.py，Redis），這裡再記錄每一次「登入失敗」，
依兩個維度鎖定一段時間：
  - 同一個帳號：WINDOW 內失敗 ACCOUNT_MAX 次 → 這個帳號暫停登入（擋「換 IP 猜同一個帳號」）
  - 同一個 IP：WINDOW 內失敗 IP_MAX 次 → 這個 IP 暫停登入（擋「同一台機器猜很多帳號」）
鎖定期間連正確密碼也不放行（不然攻擊者看回應就知道猜對了）。登入成功會清掉該帳號的失敗紀錄。
代價：別人可以故意打錯密碼把某個帳號鎖住 WINDOW 這麼久——時間短、會自己解開，可以接受。

紀錄存在 Mongo（login_failures，at 上有 TTL 索引自動清掉，見 src/mongo.py）。
scope 區分後台（admin）跟玩家（player），兩邊帳號名稱可能一樣但不是同一個帳號。
"""

from datetime import datetime, timedelta
from typing import Optional

from src.mongo import get_db

COLLECTION = 'login_failures'
WINDOW = timedelta(minutes=15)
ACCOUNT_MAX = 5
IP_MAX = 20


def _col():
    return get_db()[COLLECTION]


def _account_key(account: str) -> str:
    return (account or '').strip().lower()


def _remaining(query: dict, limit: int, now: datetime) -> int:
    """失敗次數到上限就回傳還要鎖幾秒（從最近一次失敗起算 WINDOW），沒鎖回 0。"""
    since = now - WINDOW
    q = {**query, 'at': {'$gte': since}}
    if _col().count_documents(q) < limit:
        return 0
    latest = next(iter(_col().find(q, {'at': 1}).sort('at', -1).limit(1)), None)
    if not latest:
        return 0
    return max(0, int((latest['at'] + WINDOW - now).total_seconds()) + 1)


def locked_seconds(scope: str, account: str, ip: Optional[str]) -> int:
    """這次登入要不要擋：回傳還要等幾秒（0＝可以試）。"""
    now = datetime.utcnow()
    acc = _remaining({'scope': scope, 'account': _account_key(account)}, ACCOUNT_MAX, now) if account else 0
    by_ip = _remaining({'ip': ip}, IP_MAX, now) if ip else 0
    return max(acc, by_ip)


def record_failure(scope: str, account: str, ip: Optional[str]) -> None:
    _col().insert_one({'scope': scope, 'account': _account_key(account), 'ip': ip, 'at': datetime.utcnow()})


def clear(scope: str, account: str) -> None:
    """登入成功：清掉這個帳號的失敗紀錄（IP 的不清，免得用一個自己的帳號洗掉 IP 計數）。"""
    _col().delete_many({'scope': scope, 'account': _account_key(account)})


def locked_message(seconds: int) -> str:
    minutes = max(1, -(-seconds // 60))
    return f'登入失敗次數太多，請 {minutes} 分鐘後再試'
