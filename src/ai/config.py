"""AI 問答的後台設定（app_settings 的 ai_config 一筆）。

API key 是機密：status() 只回「有沒有設定、末 4 碼」，不會把完整 key 回給前端，也不寫進操作紀錄。
"""

from datetime import datetime

from src.mongo import get_db

CONFIG_ID = 'ai_config'
KEY_MAX = 300
MODEL_MAX = 100

#: 支援的供應商（OpenAI 相容 API）；模型名稱後台可以改，這裡只是預設值
PROVIDERS = {
    'gemini': {
        'label': 'Google Gemini',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai',
        'default_model': 'gemini-2.5-flash',
        'key_url': 'https://aistudio.google.com/apikey',
    },
    'groq': {
        'label': 'Groq',
        'base_url': 'https://api.groq.com/openai/v1',
        'default_model': 'llama-3.3-70b-versatile',
        'key_url': 'https://console.groq.com/keys',
    },
}
DEFAULT_ORDER = ['gemini', 'groq']
DEFAULT_LIMITS = {'user_per_minute': 3, 'user_per_day': 50}


def _col():
    return get_db()['app_settings']


def _mask(key: str) -> str:
    return '••••' + key[-4:] if len(key) > 4 else '••••'


def load() -> dict:
    """完整設定（含 API key，只給後端用）。缺的欄位補預設值。"""
    doc = _col().find_one({'_id': CONFIG_ID}) or {}
    saved = doc.get('providers') or {}
    providers = {}
    for key, meta in PROVIDERS.items():
        p = saved.get(key) or {}
        providers[key] = {
            'enabled': p.get('enabled', True) is not False,
            'api_key': (p.get('api_key') or '').strip(),
            'model': (p.get('model') or '').strip() or meta['default_model'],
        }
    order = [k for k in (doc.get('order') or []) if k in PROVIDERS]
    order += [k for k in DEFAULT_ORDER if k not in order]
    return {
        'enabled': bool(doc.get('enabled', False)),
        'order': order,
        'providers': providers,
        'user_per_minute': int(doc.get('user_per_minute') or DEFAULT_LIMITS['user_per_minute']),
        'user_per_day': int(doc.get('user_per_day') or DEFAULT_LIMITS['user_per_day']),
        'updated_at': doc.get('updated_at'),
        'updated_by': doc.get('updated_by'),
    }


def active_providers() -> list:
    """照順序、有啟用且有 key 的供應商：[{key, label, base_url, model, api_key}]。"""
    cfg = load()
    out = []
    for key in cfg['order']:
        p = cfg['providers'][key]
        if p['enabled'] and p['api_key']:
            out.append({'key': key, 'label': PROVIDERS[key]['label'], 'base_url': PROVIDERS[key]['base_url'],
                        'model': p['model'], 'api_key': p['api_key']})
    return out


def status() -> dict:
    """給後台看的設定（key 只給末 4 碼）。"""
    cfg = load()
    return {
        'enabled': cfg['enabled'],
        'order': cfg['order'],
        'user_per_minute': cfg['user_per_minute'],
        'user_per_day': cfg['user_per_day'],
        'updated_at': cfg['updated_at'],
        'updated_by': cfg['updated_by'],
        'providers': [{
            'key': key, 'label': PROVIDERS[key]['label'], 'key_url': PROVIDERS[key]['key_url'],
            'default_model': PROVIDERS[key]['default_model'],
            'enabled': cfg['providers'][key]['enabled'], 'model': cfg['providers'][key]['model'],
            'has_key': bool(cfg['providers'][key]['api_key']),
            'masked_key': _mask(cfg['providers'][key]['api_key']) if cfg['providers'][key]['api_key'] else '',
        } for key in cfg['order']],
    }


def update(data: dict, updated_by: str = '') -> dict:
    """部分更新：enabled、order、user_per_minute、user_per_day、providers.{key}.{enabled, model, api_key}。

    api_key：沒帶＝不動，空字串＝清掉。格式不對丟 ValueError（訊息直接給管理員看）。
    """
    if not isinstance(data, dict):
        raise ValueError('設定格式錯誤')
    sets: dict = {}
    if 'enabled' in data:
        sets['enabled'] = bool(data['enabled'])
    if 'order' in data:
        order = data['order']
        if not isinstance(order, list) or any(k not in PROVIDERS for k in order) or len(set(order)) != len(order):
            raise ValueError('供應商順序格式錯誤')
        sets['order'] = order + [k for k in DEFAULT_ORDER if k not in order]
    for field, lo, hi in (('user_per_minute', 1, 60), ('user_per_day', 1, 5000)):
        if field in data:
            try:
                value = int(data[field])
            except (TypeError, ValueError):
                raise ValueError('限流次數要是數字')
            if not lo <= value <= hi:
                raise ValueError(f'限流次數要在 {lo}–{hi} 之間')
            sets[field] = value
    providers = data.get('providers')
    if providers is not None:
        if not isinstance(providers, dict) or any(k not in PROVIDERS for k in providers):
            raise ValueError('供應商設定格式錯誤')
        for key, p in providers.items():
            if not isinstance(p, dict):
                raise ValueError('供應商設定格式錯誤')
            if 'enabled' in p:
                sets[f'providers.{key}.enabled'] = bool(p['enabled'])
            if 'model' in p:
                model = (p['model'] or '').strip() if isinstance(p['model'], str) else None
                if model is None or len(model) > MODEL_MAX or any(c.isspace() for c in model):
                    raise ValueError(f'{PROVIDERS[key]["label"]} 的模型名稱格式錯誤')
                sets[f'providers.{key}.model'] = model
            if 'api_key' in p:
                api_key = p['api_key'].strip() if isinstance(p['api_key'], str) else None
                if api_key is None or len(api_key) > KEY_MAX or any(c.isspace() for c in api_key):
                    raise ValueError(f'{PROVIDERS[key]["label"]} 的 API key 格式錯誤')
                sets[f'providers.{key}.api_key'] = api_key
    if sets:
        sets['updated_at'] = datetime.utcnow()
        sets['updated_by'] = updated_by or None
        _col().update_one({'_id': CONFIG_ID}, {'$set': sets}, upsert=True)
    return status()
