"""AI 問答（src/ai/）：設定遮蔽 key、供應商輪換與冷卻、工具呼叫、每人限流、後台 API。

不會真的連外：把 router._post 換成假的回應。
"""
import json

import pytest

from src.ai import ask, config, router, tools
from src.mongo import get_db


def _setup(enabled=True, keys=('gemini', 'groq')):
    config.update({'enabled': enabled, 'providers': {k: {'api_key': f'key-{k}-1234'} for k in keys}})


def _answer(text):
    return {'choices': [{'message': {'role': 'assistant', 'content': text}}]}


def _tool_call(name, args):
    return {'choices': [{'message': {'role': 'assistant', 'content': '', 'tool_calls': [
        {'id': 'c1', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}}]}


def test_config_masks_keys_and_keeps_unset(app):
    _setup()
    st = config.status()
    gem = next(p for p in st['providers'] if p['key'] == 'gemini')
    assert gem['has_key'] and gem['masked_key'] == '••••1234'
    assert 'api_key' not in gem
    config.update({'providers': {'gemini': {'model': 'gemini-x'}}})
    assert config.load()['providers']['gemini']['api_key'] == 'key-gemini-1234', '沒帶 api_key 不動'
    config.update({'providers': {'gemini': {'api_key': ''}}})
    assert not config.load()['providers']['gemini']['api_key']
    with pytest.raises(ValueError):
        config.update({'order': ['nope']})


def test_rotation_on_rate_limit(app, monkeypatch):
    _setup()
    calls = []

    def fake_post(provider, payload):
        calls.append(provider['key'])
        if provider['key'] == 'gemini':
            raise router.ProviderError('429', 60)
        return _answer('好')
    monkeypatch.setattr(router, '_post', fake_post)
    result = ask.ask('你好')
    assert result['answer'] == '好' and result['providers'] == ['groq']
    # gemini 冷卻中：下一次直接跳過
    calls.clear()
    ask.ask('再問一次')
    assert calls == ['groq']
    assert router.runtime_status()['gemini']['cooldown'] > 0


def test_all_busy(app, monkeypatch):
    _setup()

    def fake_post(provider, payload):
        raise router.ProviderError('500', 30)
    monkeypatch.setattr(router, '_post', fake_post)
    with pytest.raises(ask.AskError):
        ask.ask('你好')
    assert get_db()['ai_logs'].find_one({'ok': False})


def test_tool_loop(app, monkeypatch):
    _setup()
    replies = iter([_tool_call('find_ship_holders', {'name': 'Nothing'}), _answer('沒人有')])
    seen = []

    def fake_post(provider, payload):
        seen.append(payload['messages'])
        return next(replies)
    monkeypatch.setattr(router, '_post', fake_post)
    result = ask.ask('誰有 Nothing？')
    assert result['answer'] == '沒人有'
    assert result['tools'][0]['name'] == 'find_ship_holders'
    tool_msg = seen[1][-1]
    assert tool_msg['role'] == 'tool' and json.loads(tool_msg['content'])['found'] is False


def test_tool_run_rejects_unknown_and_bad_args(app):
    assert 'error' in json.loads(tools.run('drop_database', '{}'))
    assert 'error' in json.loads(tools.run('find_item_holders', 'not json'))


def test_disabled_blocks_discord_but_not_admin(app, monkeypatch):
    _setup(enabled=False)
    monkeypatch.setattr(router, '_post', lambda p, payload: _answer('ok'))
    with pytest.raises(ask.AskError):
        ask.ask('hi', source='discord')
    assert ask.ask('hi', source='admin')['answer'] == 'ok'


def test_user_rate_limit(app):
    config.update({'user_per_minute': 2})
    ask.check_rate('discord:1')
    ask.check_rate('discord:1')
    with pytest.raises(ask.AskError):
        ask.check_rate('discord:1')


def test_admin_api(client, auth_headers, monkeypatch):
    res = client.put('/data/ai/config', headers=auth_headers,
                     json={'enabled': True, 'order': ['groq', 'gemini'], 'providers': {'groq': {'api_key': 'gsk-abcd9999'}}})
    assert res.status_code == 200, res.get_data(as_text=True)
    data = res.get_json()['data']
    assert data['order'][0] == 'groq' and data['providers'][0]['masked_key'] == '••••9999'
    assert 'gsk-abcd9999' not in res.get_data(as_text=True)
    monkeypatch.setattr(router, '_post', lambda p, payload: _answer('測試成功'))
    res = client.post('/data/ai/test', headers=auth_headers, json={'question': '你好'})
    assert res.get_json()['data']['answer'] == '測試成功'
    assert client.get('/data/ai/logs', headers=auth_headers).get_json()['data'][0]['question'] == '你好'
    assert client.get('/data/ai/config').status_code in (401, 422)


def test_tools_run_on_real_models(client, auth_headers):
    """工具直接跑在真的模型上（不經 AI）：有資料查得到、沒資料回 found=False，不會丟例外。"""
    from src.models.item import ItemMaster
    from src.models.player import Player
    db = get_db()
    db['item_master'].insert_one({'_id': 'item-x', 'name': 'Agricium', 'name_lower': 'agricium', 'name_zh': '農業金屬',
                                  'type': 'Commodity', 'is_current': True})
    Player.create(player_name='Tom Li', star_citizen_id='TomLi', nickname='湯姆')
    assert client.post('/inventory/add', headers=auth_headers,
                       json={'item': 'item-x', 'quantity': 40, 'location': 'Area18',
                             'owner_type': 'player', 'player': 'TomLi'}).status_code in (200, 201)
    hit = json.loads(tools.run('find_item_holders', {'name': 'agri'}))
    assert hit['found'] and hit['items'][0]['holders'][0]['holder'] == '湯姆（TomLi）'
    assert json.loads(tools.run('player_summary', {'player': '湯姆'}))['items'][0]['quantity'] == 40
    for name, args in (('find_blueprint_holders', {'name': 'x'}), ('find_ship_holders', {'name': 'x'}),
                       ('where_to_buy', {'name': 'agri'}), ('player_summary', {'player': 'nobody'})):
        json.loads(tools.run(name, args))
    assert ItemMaster.get('item-x')
