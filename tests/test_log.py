"""GET /log/ 的 API 測試。"""
from src.models.log import Log


class TestLogList:
    def test_requires_auth(self, client):
        assert client.get('/log/').status_code == 401

    def test_returns_data_and_total(self, client, auth_headers, seed_admin):
        Log.create('admin', 'login', success=True)
        resp = client.get('/log/', headers=auth_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert 'data' in body
        assert 'total' in body
        assert len(body['data']) >= 1

    def test_limit_parameter(self, client, auth_headers, seed_admin):
        for i in range(5):
            Log.create('admin', f'action{i}')
        resp = client.get('/log/?limit=3', headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.get_json()['data']) <= 3

    def test_username_filter(self, client, auth_headers, seed_admin):
        Log.create('alice', 'act')
        Log.create('bob', 'act')
        resp = client.get('/log/?username=alice', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert all(l['username'] == 'alice' for l in data)
