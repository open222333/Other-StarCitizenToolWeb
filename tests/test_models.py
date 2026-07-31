"""src/models/* 的單元測試。外部依賴由 conftest.py 的 mock 替換。"""
import pytest
from src.models.user import User
from src.models.user_template import UserTemplate
from src.models.log import Log
from src.models.device_token import DeviceToken


# ─────────────────────────────────────────────
#  UserTemplate
# ─────────────────────────────────────────────

class TestUserTemplate:
    def test_ensure_defaults_creates_system_template(self):
        tid = UserTemplate.ensure_defaults()
        tmpl = UserTemplate.find_by_id(tid)
        assert tmpl is not None
        assert tmpl['is_system'] is True
        assert tmpl['role'] == 'admin'

    def test_ensure_defaults_is_idempotent(self):
        tid1 = UserTemplate.ensure_defaults()
        tid2 = UserTemplate.ensure_defaults()
        assert tid1 == tid2

    def test_create_and_find_by_id(self):
        tid = UserTemplate.create('操作員', role='operator', description='for testing')
        tmpl = UserTemplate.find_by_id(tid)
        assert tmpl['name'] == '操作員'
        assert tmpl['role'] == 'operator'
        assert tmpl['description'] == 'for testing'
        assert tmpl['is_system'] is False

    def test_find_all_system_template_first(self):
        UserTemplate.ensure_defaults()
        UserTemplate.create('一般', role='viewer')
        templates = UserTemplate.find_all()
        assert len(templates) >= 2
        assert templates[0]['is_system'] is True

    def test_update_name_and_role(self):
        tid = UserTemplate.create('原始', role='viewer')
        assert UserTemplate.update(tid, name='更新後', role='operator') is True
        tmpl = UserTemplate.find_by_id(tid)
        assert tmpl['name'] == '更新後'
        assert tmpl['role'] == 'operator'

    def test_delete_ok(self):
        tid = UserTemplate.create('可刪除', role='viewer')
        assert UserTemplate.delete(tid) == 'ok'
        assert UserTemplate.find_by_id(tid) is None

    def test_delete_system_returns_system(self):
        tid = UserTemplate.ensure_defaults()
        assert UserTemplate.delete(tid) == 'system'

    def test_delete_not_found(self):
        assert UserTemplate.delete('000000000000000000000000') == 'not_found'


# ─────────────────────────────────────────────
#  User
# ─────────────────────────────────────────────

class TestUser:
    def setup_method(self):
        self._tid = UserTemplate.create('測試模板', role='operator')

    def test_create_returns_string_id(self):
        uid = User.create('alice', 'password123', role='operator', template_id=self._tid)
        assert isinstance(uid, str) and len(uid) > 0

    def test_find_by_username_includes_password(self):
        User.create('bob', 'pass123', role='viewer', template_id=self._tid)
        user = User.find_by_username('bob')
        assert user is not None
        assert user['username'] == 'bob'
        assert 'password' in user   # 供 auth view 驗密用

    def test_find_by_username_not_found_returns_none(self):
        assert User.find_by_username('nobody') is None

    def test_find_by_id_excludes_password(self):
        uid = User.create('carol', 'pass123', role='viewer', template_id=self._tid)
        user = User.find_by_id(uid)
        assert user is not None
        assert 'password' not in user

    def test_find_all_excludes_passwords(self):
        User.create('dave', 'pass123', role='viewer', template_id=self._tid)
        User.create('eve', 'pass456', role='operator', template_id=self._tid)
        users = User.find_all()
        assert len(users) >= 2
        assert all('password' not in u for u in users)

    def test_check_password_correct(self):
        User.create('frank', 'mypassword', role='viewer', template_id=self._tid)
        raw = User.find_by_username('frank')
        assert User.check_password('mypassword', raw['password']) is True

    def test_check_password_wrong(self):
        User.create('grace', 'mypassword', role='viewer', template_id=self._tid)
        raw = User.find_by_username('grace')
        assert User.check_password('wrongpass', raw['password']) is False

    def test_update_password(self):
        uid = User.create('henry', 'oldpass', role='viewer', template_id=self._tid)
        User.update(uid, password='newpass')
        raw = User.find_by_username('henry')
        assert User.check_password('newpass', raw['password']) is True
        assert User.check_password('oldpass', raw['password']) is False

    def test_update_role(self):
        uid = User.create('ivan', 'pass123', role='viewer', template_id=self._tid)
        User.update(uid, role='operator')
        assert User.find_by_id(uid)['role'] == 'operator'

    def test_delete_ok(self):
        uid = User.create('judy', 'pass123', role='viewer', template_id=self._tid)
        assert User.delete(uid) == 'ok'
        assert User.find_by_id(uid) is None

    def test_delete_admin_returns_protected(self):
        uid = User.create('admin', 'pass123', role='admin', template_id=self._tid)
        assert User.delete(uid) == 'protected'

    def test_delete_not_found(self):
        assert User.delete('000000000000000000000000') == 'not_found'

    def test_update_role_by_template(self):
        uid1 = User.create('k1', 'pass123', role='operator', template_id=self._tid)
        uid2 = User.create('k2', 'pass456', role='operator', template_id=self._tid)
        count = User.update_role_by_template(self._tid, 'viewer')
        assert count == 2
        assert User.find_by_id(uid1)['role'] == 'viewer'
        assert User.find_by_id(uid2)['role'] == 'viewer'


# ─────────────────────────────────────────────
#  Log
# ─────────────────────────────────────────────

class TestLog:
    def test_create_returns_id(self):
        lid = Log.create('admin', 'test_action', detail='testing', success=True)
        assert lid is not None

    def test_find_all(self):
        Log.create('alice', 'action1', success=True)
        Log.create('bob', 'action2', success=False)
        logs = Log.find_all()
        assert len(logs) >= 2
        assert all('created_at' in l for l in logs)

    def test_find_all_username_filter(self):
        Log.create('alice', 'login')
        Log.create('bob', 'login')
        Log.create('alice', 'logout')
        logs = Log.find_all(username='alice')
        assert len(logs) == 2
        assert all(l['username'] == 'alice' for l in logs)

    def test_count(self):
        Log.create('u1', 'a')
        Log.create('u2', 'b')
        assert Log.count() >= 2

    def test_count_username_filter(self):
        Log.create('alice', 'a1')
        Log.create('bob', 'a2')
        Log.create('alice', 'a3')
        assert Log.count(username='alice') == 2
        assert Log.count(username='bob') == 1

    def test_pagination(self):
        for i in range(6):
            Log.create('user', f'action{i}')
        page1 = Log.find_all(limit=4, offset=0)
        page2 = Log.find_all(limit=4, offset=4)
        assert len(page1) == 4
        assert len(page2) == 2


# ─────────────────────────────────────────────
#  DeviceToken
# ─────────────────────────────────────────────

class TestDeviceToken:
    def test_register_and_find(self):
        DeviceToken.register('user1', 'token_abc', 'ios', '1.0.0')
        tokens = DeviceToken.find_by_username('user1')
        assert len(tokens) == 1
        assert tokens[0]['token'] == 'token_abc'
        assert tokens[0]['platform'] == 'ios'

    def test_register_upsert_updates_app_version(self):
        DeviceToken.register('user1', 'token_xyz', 'android', '1.0')
        DeviceToken.register('user1', 'token_xyz', 'android', '2.0')
        tokens = DeviceToken.find_by_username('user1')
        assert len(tokens) == 1
        assert tokens[0]['app_version'] == '2.0'

    def test_multiple_tokens_per_user(self):
        DeviceToken.register('user1', 'tok_a', 'ios', '1.0')
        DeviceToken.register('user1', 'tok_b', 'android', '1.0')
        assert len(DeviceToken.find_by_username('user1')) == 2

    def test_unregister_returns_true(self):
        DeviceToken.register('user1', 'del_tok', 'web', '')
        assert DeviceToken.unregister('del_tok') is True
        tokens = DeviceToken.find_by_username('user1')
        assert not any(t['token'] == 'del_tok' for t in tokens)

    def test_find_by_platform(self):
        DeviceToken.register('user1', 'ios_tok', 'ios', '1.0')
        DeviceToken.register('user1', 'and_tok', 'android', '1.0')
        ios = DeviceToken.find_by_platform('user1', 'ios')
        assert len(ios) == 1
        assert ios[0]['platform'] == 'ios'
