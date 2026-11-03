"""物品類型分組（src/models/app_setting.py 的 ItemTypeGroups，GET／PUT /item/type-groups）。"""
from src.models.app_setting import DEFAULT_ITEM_TYPE_GROUPS


def test_default_set_and_reset(client, auth_headers):
    data = client.get('/item/type-groups').get_json()['data']
    assert data['custom'] is False and data['groups'] == DEFAULT_ITEM_TYPE_GROUPS
    body = {'groups': [{'label': ' 組件 ', 'types': ['Shield', 'Cooler', 'Shield'], 'prefixes': []},
                       {'label': '護甲', 'types': [], 'prefixes': ['Char_Armor_']}]}
    res = client.put('/item/type-groups', json=body, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['data'] == {'custom': True, 'groups': [
        {'label': '組件', 'types': ['Shield', 'Cooler'], 'prefixes': []},
        {'label': '護甲', 'types': [], 'prefixes': ['Char_Armor_']}]}
    assert client.get('/item/type-groups').get_json()['data']['groups'][0]['label'] == '組件'
    res = client.put('/item/type-groups', json={'groups': []}, headers=auth_headers)
    assert res.get_json()['data']['custom'] is False


def test_validation(client, auth_headers):
    bad = [
        [{'label': '', 'types': ['Shield']}],
        [{'label': '其他', 'types': ['Shield']}],
        [{'label': 'A', 'types': ['Shield']}, {'label': 'A', 'types': []}],
        [{'label': 'A', 'types': ['Shield']}, {'label': 'B', 'types': ['Shield']}],
        [{'label': 'A', 'types': ['<script>']}],
        [{'label': 'A', 'types': 'Shield'}],
        [{'label': 'A' * 21, 'types': []}],
    ]
    for groups in bad:
        res = client.put('/item/type-groups', json={'groups': groups}, headers=auth_headers)
        assert res.status_code == 400, groups
