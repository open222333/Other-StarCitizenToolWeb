"""API 文件（Swagger）：每個端點 docstring 的 YAML 都要能解析、規格產得出來，而且只給後台 admin 看。"""
import inspect

import yaml


def test_every_docstring_yaml_parses(app):
    """docstring 裡 `---` 以下是 YAML：寫壞一個，整份 API 文件就 500（曾經因為 `{英文: 翻譯}` 沒加引號壞掉）。"""
    bad = []
    for rule in app.url_map.iter_rules():
        doc = inspect.getdoc(app.view_functions.get(rule.endpoint)) or ''
        if '---' not in doc:
            continue
        try:
            yaml.safe_load(doc.split('---', 1)[1])
        except yaml.YAMLError as err:
            bad.append(f'{rule.rule}: {str(err).splitlines()[0]}')
    assert not bad, '這些端點的 Swagger YAML 寫壞了：\n' + '\n'.join(bad)


def test_admin_gets_spec(client, auth_headers):
    body = client.get('/data/api-spec', headers=auth_headers).get_json()
    assert body['success']
    spec = body['data']
    assert spec['swagger'] == '2.0'
    assert '/data/api-spec' in spec['paths']
    assert len(spec['paths']) > 50
    assert 'My API' not in spec['info']['title']


def test_spec_is_not_public(client, app):
    from src.models.user import User
    from src.models.user_template import UserTemplate
    assert client.get('/data/api-spec').status_code == 401
    assert client.get('/apispec_1.json').status_code == 401
    assert client.get('/apidocs/').status_code == 401
    # 非 admin 的後台帳號也不行
    User.create('viewer1', 'Viewer1234!', role='viewer', template_id=UserTemplate.ensure_defaults())
    token = client.post('/auth/login', json={'username': 'viewer1', 'password': 'Viewer1234!'}).get_json()['token']
    assert client.get('/data/api-spec', headers={'Authorization': f'Bearer {token}'}).status_code == 403


def test_swagger_ui_still_works_with_admin_token(client, auth_headers):
    assert client.get('/apispec_1.json', headers=auth_headers).status_code == 200
