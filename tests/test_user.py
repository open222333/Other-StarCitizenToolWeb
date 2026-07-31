"""GET|POST|PUT|DELETE /user/* 及 /user/templates/* 的 API 測試。"""
from src.models.user import User
from src.models.user_template import UserTemplate


def _tmpl(name='Test', role='operator'):
    return UserTemplate.create(name, role=role)


class TestListUsers:
    def test_admin_can_list(self, client, auth_headers, seed_admin):
        resp = client.get('/user/', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data['data'], list)

    def test_no_auth_returns_401(self, client):
        assert client.get('/user/').status_code == 401

    def test_non_admin_returns_403(self, client, seed_admin):
        tid = _tmpl('Viewer', 'viewer')
        User.create('viewer', 'ViewPass1!', role='viewer', template_id=tid)
        token = client.post('/auth/login', json={
            'username': 'viewer', 'password': 'ViewPass1!',
        }).get_json()['token']
        assert client.get('/user/', headers={
            'Authorization': f'Bearer {token}',
        }).status_code == 403


class TestCreateUser:
    def test_success(self, client, auth_headers, seed_admin):
        tid = _tmpl('Op', 'operator')
        resp = client.post('/user/', headers=auth_headers, json={
            'username': 'newuser',
            'password': 'NewPass1!',
            'template_id': tid,
        })
        assert resp.status_code == 201
        assert 'id' in resp.get_json()

    def test_duplicate_username_returns_409(self, client, auth_headers, seed_admin):
        tid = _tmpl('Op2', 'operator')
        payload = {'username': 'dup', 'password': 'Pass1234!', 'template_id': tid}
        client.post('/user/', headers=auth_headers, json=payload)
        assert client.post('/user/', headers=auth_headers, json=payload).status_code == 409

    def test_password_too_short_returns_400(self, client, auth_headers, seed_admin):
        tid = _tmpl('Op3', 'operator')
        resp = client.post('/user/', headers=auth_headers, json={
            'username': 'shortpw', 'password': 'abc', 'template_id': tid,
        })
        assert resp.status_code == 400

    def test_username_too_short_returns_400(self, client, auth_headers, seed_admin):
        tid = _tmpl('Op4', 'operator')
        resp = client.post('/user/', headers=auth_headers, json={
            'username': 'ab', 'password': 'ValidPass1!', 'template_id': tid,
        })
        assert resp.status_code == 400

    def test_missing_template_id_returns_400(self, client, auth_headers, seed_admin):
        resp = client.post('/user/', headers=auth_headers, json={
            'username': 'notmpl', 'password': 'ValidPass1!',
        })
        assert resp.status_code == 400

    def test_invalid_template_id_returns_404(self, client, auth_headers, seed_admin):
        resp = client.post('/user/', headers=auth_headers, json={
            'username': 'badtmpl',
            'password': 'ValidPass1!',
            'template_id': '000000000000000000000000',
        })
        assert resp.status_code == 404


class TestUpdateUser:
    def test_update_password_success(self, client, auth_headers, seed_admin):
        tid = _tmpl('Up', 'viewer')
        uid = User.create('upduser', 'OldPass1!', role='viewer', template_id=tid)
        resp = client.put(f'/user/{uid}', headers=auth_headers, json={
            'password': 'NewPass2!',
        })
        assert resp.status_code == 200
        # 新密碼可以登入
        assert client.post('/auth/login', json={
            'username': 'upduser', 'password': 'NewPass2!',
        }).status_code == 200

    def test_update_nonexistent_user_returns_404(self, client, auth_headers, seed_admin):
        assert client.put('/user/000000000000000000000000', headers=auth_headers, json={
            'password': 'NewPass2!',
        }).status_code == 404


class TestDeleteUser:
    def test_delete_success(self, client, auth_headers, seed_admin):
        tid = _tmpl('Del', 'viewer')
        uid = User.create('deluser', 'DelPass1!', role='viewer', template_id=tid)
        assert client.delete(f'/user/{uid}', headers=auth_headers).status_code == 200

    def test_cannot_delete_self_returns_400(self, client, seed_admin):
        token = client.post('/auth/login', json={
            'username': 'admin', 'password': 'Admin1234!',
        }).get_json()['token']
        uid = str(User.find_by_username('admin')['_id'])
        assert client.delete(f'/user/{uid}', headers={
            'Authorization': f'Bearer {token}',
        }).status_code == 400

    def test_cannot_delete_protected_admin_returns_403(self, client, seed_admin):
        # 用另一個 admin 帳號來刪 admin（繞過 self-delete 檢查）
        tid2 = _tmpl('Admin2', 'admin')
        User.create('admin2', 'Admin2Pass!', role='admin', template_id=tid2)
        token2 = client.post('/auth/login', json={
            'username': 'admin2', 'password': 'Admin2Pass!',
        }).get_json()['token']
        uid = str(User.find_by_username('admin')['_id'])
        assert client.delete(f'/user/{uid}', headers={
            'Authorization': f'Bearer {token2}',
        }).status_code == 403


class TestUserTemplates:
    def test_list_templates(self, client, auth_headers, seed_admin):
        resp = client.get('/user/templates/', headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.get_json()['data'], list)

    def test_create_template_success(self, client, auth_headers, seed_admin):
        resp = client.post('/user/templates/', headers=auth_headers, json={
            'name': '新模板', 'role': 'operator', 'description': '測試用',
        })
        assert resp.status_code == 201
        assert 'id' in resp.get_json()

    def test_create_template_invalid_role_returns_400(self, client, auth_headers, seed_admin):
        resp = client.post('/user/templates/', headers=auth_headers, json={
            'name': '壞模板', 'role': 'superuser',
        })
        assert resp.status_code == 400

    def test_update_template_syncs_user_role(self, client, auth_headers, seed_admin):
        tid = _tmpl('ToUpdate', 'viewer')
        uid = User.create('syncuser', 'Pass1234!', role='viewer', template_id=tid)
        resp = client.put(f'/user/templates/{tid}', headers=auth_headers, json={
            'role': 'operator',
        })
        assert resp.status_code == 200
        assert resp.get_json()['synced_users'] == 1
        from src.models.user import User as U
        assert U.find_by_id(uid)['role'] == 'operator'

    def test_delete_system_template_returns_403(self, client, auth_headers, seed_admin):
        tid = UserTemplate.ensure_defaults()
        assert client.delete(f'/user/templates/{tid}', headers=auth_headers).status_code == 403

    def test_delete_template_success(self, client, auth_headers, seed_admin):
        tid = _tmpl('Deletable', 'viewer')
        assert client.delete(f'/user/templates/{tid}', headers=auth_headers).status_code == 200
