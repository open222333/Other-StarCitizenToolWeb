"""POST /device/register 及 /device/unregister 的 API 測試。"""


class TestDeviceRegister:
    def test_register_success(self, client, auth_headers, seed_admin):
        resp = client.post('/device/register', headers=auth_headers, json={
            'token': 'fcm_token_abc123',
            'platform': 'ios',
            'app_version': '1.0.0',
        })
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_register_requires_auth(self, client):
        assert client.post('/device/register', json={
            'token': 'tok', 'platform': 'ios',
        }).status_code == 401

    def test_missing_token_returns_400(self, client, auth_headers, seed_admin):
        resp = client.post('/device/register', headers=auth_headers, json={
            'platform': 'ios',
        })
        assert resp.status_code == 400


class TestDeviceUnregister:
    def test_unregister_success(self, client, auth_headers, seed_admin):
        client.post('/device/register', headers=auth_headers, json={
            'token': 'del_token_xyz', 'platform': 'android',
        })
        resp = client.post('/device/unregister', headers=auth_headers, json={
            'token': 'del_token_xyz',
        })
        assert resp.status_code == 200

    def test_unregister_requires_auth(self, client):
        assert client.post('/device/unregister', json={
            'token': 'tok',
        }).status_code == 401
