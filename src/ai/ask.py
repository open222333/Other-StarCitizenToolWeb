"""一次 AI 問答：送出問題 → AI 決定呼叫哪些工具 → 執行 → 交回 AI，最多 MAX_ROUNDS 輪 → 中文答案。

紀錄寫 ai_logs（問題、提問者、用了哪幾家、呼叫了哪些工具、耗時、成功與否；30 天 TTL）。
每人限流（Discord）：照後台設定的每分鐘／每天次數，計數放 Redis。
"""

import time
from datetime import datetime, timezone

import src.redis_client as redis_client
from src.ai import config, router, tools
from src.mongo import get_db

MAX_ROUNDS = 4
QUESTION_MAX = 500
LOGS = 'ai_logs'

SYSTEM_PROMPT = (
    '你是星際公民（Star Citizen）公會工具網站的助理，用繁體中文回答。\n'
    '公會資料（誰有什麼物品、藍圖、船艦，物品或商品在哪裡買）一定要用工具查，只根據工具查到的資料回答；'
    '查不到就說查不到，不要猜，也不要編數字。\n'
    '數量、地點、玩家名稱照工具結果原樣寫；物品名稱有中文就用中文，必要時附英文。\n'
    '回答簡短，用條列；超過 10 筆只列前 10 筆並說還有多少。\n'
    '跟遊戲或公會資料無關的問題，簡短說明你只能回答公會資料相關的問題。'
)


class AskError(Exception):
    """給使用者看的錯誤（停用、限流、全部供應商都忙）。"""


def _limit_key(user: str, span: str) -> str:
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M' if span == 'm' else '%Y%m%d')
    return f'ai:user:{user}:{span}:{stamp}'


def check_rate(user: str) -> None:
    """每人限流，超過丟 AskError。Redis 不能用時不擋（不要因為 Redis 掛掉整個功能停擺）。"""
    if not user:
        return
    cfg = config.load()
    try:
        r = redis_client.get_redis()
        for span, limit, ttl, text in (('m', cfg['user_per_minute'], 70, '每分鐘'),
                                       ('d', cfg['user_per_day'], 90000, '每天')):
            key = _limit_key(user, span)
            count = r.incr(key)
            if count == 1:
                r.expire(key, ttl)
            if count > limit:
                raise AskError(f'問太快了：{text}最多 {limit} 次，請稍後再試。')
    except AskError:
        raise
    except Exception:
        return


def _log(entry: dict) -> None:
    try:
        get_db()[LOGS].insert_one({**entry, 'created_at': datetime.utcnow()})
    except Exception:
        pass


def ask(question: str, asker: str = '', source: str = 'discord') -> dict:
    """回傳 {answer, providers: [...], tools: [...], ms}；失敗丟 AskError。"""
    question = (question or '').strip()
    if not question:
        raise AskError('請輸入問題。')
    if len(question) > QUESTION_MAX:
        raise AskError(f'問題太長了（最多 {QUESTION_MAX} 字）。')
    if source != 'admin' and not config.load()['enabled']:
        raise AskError('AI 問答目前沒有開放。')

    start = time.time()
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': question}]
    used_providers, used_tools = [], []
    answer = ''
    try:
        for round_no in range(MAX_ROUNDS):
            # 最後一輪不給工具，逼 AI 用手上的資料作答
            message, provider = router.chat(messages, tools.TOOLS if round_no < MAX_ROUNDS - 1 else [])
            used_providers.append(provider)
            calls = message.get('tool_calls') or []
            if not calls:
                answer = (message.get('content') or '').strip()
                break
            messages.append({'role': 'assistant', 'content': message.get('content') or '', 'tool_calls': calls})
            for call in calls:
                fn = call.get('function') or {}
                used_tools.append({'name': fn.get('name'), 'arguments': fn.get('arguments')})
                messages.append({'role': 'tool', 'tool_call_id': call.get('id') or '', 'name': fn.get('name') or '',
                                 'content': tools.run(fn.get('name'), fn.get('arguments'))})
    except router.AllBusy as exc:
        _log({'question': question, 'asker': asker, 'source': source, 'providers': used_providers,
              'tools': used_tools, 'ok': False, 'error': str(exc), 'ms': int((time.time() - start) * 1000)})
        raise AskError('AI 暫時忙碌或沒有設定，請稍後再試。') from exc
    if not answer:
        answer = '抱歉，這個問題我整理不出答案，換個問法試試。'
    ms = int((time.time() - start) * 1000)
    _log({'question': question, 'asker': asker, 'source': source, 'providers': used_providers,
          'tools': used_tools, 'ok': True, 'answer': answer[:2000], 'ms': ms})
    return {'answer': answer, 'providers': used_providers, 'tools': used_tools, 'ms': ms}


def recent_logs(limit: int = 30) -> list:
    rows = get_db()[LOGS].find({}, {'_id': 0}).sort('created_at', -1).limit(max(1, min(limit, 200)))
    return list(rows)
