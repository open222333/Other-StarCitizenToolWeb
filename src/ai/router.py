"""照順序呼叫 AI 供應商（OpenAI 相容 /chat/completions），被限流或出錯就冷卻並換下一家。

冷卻與用量放 Redis（多個 worker／機器人共用）：
  ai:cooldown:<key>        有值＝冷卻中（TTL 就是冷卻秒數）
  ai:count:<key>:<日期>     今天成功呼叫次數（留 3 天）
  ai:error:<key>           最後一次錯誤（給後台看，留 1 天）
Redis 連不上時退回這個行程的記憶體（只是少了跨行程共用）。
"""

import time
from datetime import datetime, timezone

import httpx

import src.redis_client as redis_client
from src.ai import config

TIMEOUT = 25
COOLDOWN_RATE_LIMIT = 60      # 429 沒給 Retry-After 時
COOLDOWN_SERVER = 30          # 5xx／連線錯誤／逾時
COOLDOWN_CLIENT = 600         # 401／403／400：多半是 key 或模型設錯，等管理員改

_memory: dict = {}            # Redis 不能用時的備援 {key: (expire_ts, value)}


class AllBusy(Exception):
    """所有供應商都在冷卻、沒設定或都失敗。"""


class ProviderError(Exception):
    def __init__(self, message, cooldown):
        super().__init__(message)
        self.cooldown = cooldown


def _r():
    try:
        r = redis_client.get_redis()
        r.ping()
        return r
    except Exception:
        return None


def _set(name, value, ttl):
    r = _r()
    if r is not None:
        r.set(name, value, ex=max(1, int(ttl)))
    else:
        _memory[name] = (time.time() + ttl, value)


def _get(name):
    r = _r()
    if r is not None:
        return r.get(name)
    hit = _memory.get(name)
    if hit and hit[0] > time.time():
        return hit[1]
    _memory.pop(name, None)
    return None


def _ttl(name) -> int:
    r = _r()
    if r is not None:
        return max(0, int(r.ttl(name) or 0))
    hit = _memory.get(name)
    return max(0, int(hit[0] - time.time())) if hit else 0


def _today() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%d')


def _count_ok(key):
    name = f'ai:count:{key}:{_today()}'
    r = _r()
    if r is not None:
        r.incr(name)
        r.expire(name, 3 * 86400)
    else:
        exp, val = _memory.get(name, (time.time() + 3 * 86400, 0))
        _memory[name] = (exp, int(val) + 1)


def cooldown(key, seconds, message=''):
    _set(f'ai:cooldown:{key}', '1', seconds)
    if message:
        _set(f'ai:error:{key}', f'{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC {message}', 86400)


def runtime_status() -> dict:
    """每家目前狀態：冷卻剩幾秒、今天成功幾次、最後錯誤。"""
    out = {}
    for key in config.PROVIDERS:
        out[key] = {
            'cooldown': _ttl(f'ai:cooldown:{key}') if _get(f'ai:cooldown:{key}') else 0,
            'today': int(_get(f'ai:count:{key}:{_today()}') or 0),
            'last_error': _get(f'ai:error:{key}') or '',
        }
    return out


def _post(provider: dict, payload: dict) -> dict:
    """送出一次請求；把各種失敗轉成 ProviderError（帶冷卻秒數）。測試會替換這支。"""
    try:
        res = httpx.post(f"{provider['base_url']}/chat/completions", json=payload, timeout=TIMEOUT,
                         headers={'Authorization': f"Bearer {provider['api_key']}"})
    except httpx.TimeoutException:
        raise ProviderError('逾時', COOLDOWN_SERVER)
    except httpx.HTTPError as exc:
        raise ProviderError(f'連線失敗：{exc.__class__.__name__}', COOLDOWN_SERVER)
    if res.status_code == 429:
        try:
            wait = int(float(res.headers.get('retry-after') or COOLDOWN_RATE_LIMIT))
        except ValueError:
            wait = COOLDOWN_RATE_LIMIT
        raise ProviderError('額度用完／被限流（429）', max(5, min(wait, 86400)))
    if res.status_code >= 500:
        raise ProviderError(f'伺服器錯誤（{res.status_code}）', COOLDOWN_SERVER)
    if res.status_code >= 400:
        raise ProviderError(f'請求被拒（{res.status_code}）：{res.text[:200]}', COOLDOWN_CLIENT)
    try:
        return res.json()
    except ValueError:
        raise ProviderError('回應不是 JSON', COOLDOWN_SERVER)


def chat(messages: list, tools: list) -> tuple:
    """回傳 (assistant message dict, 供應商 key)。全部失敗丟 AllBusy。"""
    providers = config.active_providers()
    if not providers:
        raise AllBusy('還沒有設定任何 AI 供應商的 API key')
    errors = []
    for p in providers:
        if _get(f"ai:cooldown:{p['key']}"):
            errors.append(f"{p['label']} 冷卻中")
            continue
        payload = {'model': p['model'], 'messages': messages, 'temperature': 0.2}
        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = 'auto'
        try:
            body = _post(p, payload)
            choice = (body.get('choices') or [{}])[0]
            message = choice.get('message')
            if not isinstance(message, dict):
                raise ProviderError('回應格式不對', COOLDOWN_SERVER)
        except ProviderError as exc:
            cooldown(p['key'], exc.cooldown, str(exc))
            errors.append(f"{p['label']}：{exc}")
            continue
        _count_ok(p['key'])
        return message, p['key']
    raise AllBusy('；'.join(errors) or 'AI 暫時無法使用')
