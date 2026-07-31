"""POST /auth/login、POST /auth/refresh、GET /auth/me 的 API 測試。"""


class TestLogin:
    def test_success(self, client, seed_admin):
        resp = client.post('/auth/login', json={
            'username': 'admin',
            'password': 'Admin1234!',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'token' in data
        assert data['role'] == 'admin'
        assert data['template_id'] is not None

    def test_wrong_password_returns_401(self, client, seed_admin):
        resp = client.post('/auth/login', json={
            'username': 'admin',
            'password': 'wrongpass',
        })
        assert resp.status_code == 401
        assert resp.get_json()['success'] is False

    def test_nonexistent_user_returns_401(self, client):
        resp = client.post('/auth/login', json={
            'username': 'nobody',
            'password': 'somepass',
        })
        assert resp.status_code == 401

    def test_empty_username_returns_400(self, client):
        resp = client.post('/auth/login', json={'username': '', 'password': 'pass'})
        assert resp.status_code == 400

    def test_missing_password_returns_400(self, client):
        resp = client.post('/auth/login', json={'username': 'admin'})
        assert resp.status_code == 400

    def test_empty_body_returns_400(self, client):
        resp = client.post('/auth/login', json={})
        assert resp.status_code == 400

    def test_remember_me_returns_refresh_token(self, client, seed_admin):
        resp = client.post('/auth/login', json={
            'username': 'admin',
            'password': 'Admin1234!',
            'remember_me': True,
        })
        assert resp.status_code == 200
        assert 'refresh_token' in resp.get_json()

    def test_without_remember_me_no_refresh_token(self, client, seed_admin):
        resp = client.post('/auth/login', json={
            'username': 'admin',
            'password': 'Admin1234!',
        })
        assert resp.status_code == 200
        assert 'refresh_token' not in resp.get_json()


class TestAuthMe:
    def test_valid_token_returns_user_info(self, client, auth_headers, seed_admin):
        resp = client.get('/auth/me', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['username'] == 'admin'
        assert data['role'] == 'admin'
        assert data['is_protected'] is True

    def test_no_token_returns_401(self, client):
        assert client.get('/auth/me').status_code == 401

    def test_invalid_token_returns_error(self, client):
        resp = client.get('/auth/me', headers={
            'Authorization': 'Bearer invalid.token.here',
        })
        assert resp.status_code in (401, 422)


class TestRefresh:
    def test_valid_refresh_token_returns_new_access_token(self, client, seed_admin):
        login_resp = client.post('/auth/login', json={
            'username': 'admin',
            'password': 'Admin1234!',
            'remember_me': True,
        })
        refresh_token = login_resp.get_json()['refresh_token']

        resp = client.post('/auth/refresh', headers={
            'Authorization': f'Bearer {refresh_token}',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'token' in data

    def test_access_token_cannot_refresh(self, client, admin_token):
        resp = client.post('/auth/refresh', headers={
            'Authorization': f'Bearer {admin_token}',
        })
        assert resp.status_code == 422
