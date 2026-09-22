"""GET /log/、/log/usernames、/log/actions 的 API 測試。"""
from datetime import datetime, timedelta

from bson import ObjectId

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

    def test_username_filter_accepts_multiple(self, client, auth_headers, seed_admin):
        """?username=alice&username=bob 要用 $in 一次帶出兩人，不能只認第一個。"""
        Log.create('alice', 'act')
        Log.create('bob', 'act')
        Log.create('carol', 'act')
        resp = client.get('/log/?username=alice&username=bob', headers=auth_headers)
        data = resp.get_json()['data']
        assert {l['username'] for l in data} == {'alice', 'bob'}

    def test_action_filter_accepts_multiple(self, client, auth_headers, seed_admin):
        Log.create('admin', 'login')
        Log.create('admin', 'inventory_add')
        Log.create('admin', 'delete_player')
        resp = client.get('/log/?action=login&action=inventory_add', headers=auth_headers)
        data = resp.get_json()['data']
        assert {l['action'] for l in data} == {'login', 'inventory_add'}

    def test_success_filter_true_only(self, client, auth_headers, seed_admin):
        Log.create('admin', 'login', success=True)
        Log.create('admin', 'login', success=False)
        resp = client.get('/log/?success=1', headers=auth_headers)
        data = resp.get_json()['data']
        assert data and all(l['success'] is True for l in data)

    def test_success_filter_false_only(self, client, auth_headers, seed_admin):
        Log.create('admin', 'login', success=True)
        Log.create('admin', 'login', success=False)
        resp = client.get('/log/?success=0', headers=auth_headers)
        data = resp.get_json()['data']
        assert data and all(l['success'] is False for l in data)

    def test_success_filter_both_checked_means_no_filter(self, client, auth_headers, seed_admin):
        """兩個 checkbox 都勾＝不篩，不能誤判成「什麼都不符合」而回空清單。

        auth_headers fixture 本身登入時就會多寫一筆 admin/login 紀錄，所以這裡
        跟「不帶 success 參數」比總數，而不是硬編一個數字。
        """
        Log.create('admin', 'login', success=True)
        Log.create('admin', 'login', success=False)
        baseline = client.get('/log/', headers=auth_headers).get_json()['total']
        resp = client.get('/log/?success=1&success=0', headers=auth_headers)
        assert resp.get_json()['total'] == baseline

    def test_time_range_filter(self, client, auth_headers, seed_admin):
        old_id = Log.create('very_old_action', 'login')
        Log._col().update_one({'_id': ObjectId(old_id)},
                               {'$set': {'created_at': datetime(2020, 1, 1)}})
        Log.create('admin', 'very_new_action')  # 現在

        resp = client.get('/log/?since=2025-01-01', headers=auth_headers)
        usernames = {l['username'] for l in resp.get_json()['data']}
        assert 'very_old_action' not in usernames
        assert 'admin' in usernames

    def test_time_range_filter_accepts_z_suffix_iso(self, client, auth_headers, seed_admin):
        """前端 datetime-local 轉出來的值會是 ...Z 結尾（UTC），Python 3.10 的
        fromisoformat 原生不吃 Z，這裡要驗證真的有轉成功而不是被吃掉。"""
        old_id = Log.create('very_old_action', 'login')
        Log._col().update_one({'_id': ObjectId(old_id)},
                               {'$set': {'created_at': datetime(2020, 1, 1)}})
        Log.create('admin', 'very_new_action')

        resp = client.get('/log/?since=2025-01-01T00:00:00.000Z', headers=auth_headers)
        usernames = {l['username'] for l in resp.get_json()['data']}
        assert 'very_old_action' not in usernames
        assert 'admin' in usernames

    def test_bad_time_range_is_ignored_not_500(self, client, auth_headers, seed_admin):
        Log.create('admin', 'login')
        resp = client.get('/log/?since=not-a-date', headers=auth_headers)
        assert resp.status_code == 200

    def test_sort_dir_asc(self, client, auth_headers, seed_admin):
        """預設是新到舊；sort_dir=asc 要反過來變舊到新。

        auth_headers fixture 本身也會留一筆紀錄，所以只看我們自己這兩筆
        （用專屬的 action 名稱挑出來）的相對順序，不管它排在第幾個。
        """
        first_id = Log.create('admin', 'zz_first_action')
        Log._col().update_one({'_id': ObjectId(first_id)},
                               {'$set': {'created_at': datetime.utcnow() - timedelta(days=1)}})
        Log.create('admin', 'zz_second_action')

        resp = client.get('/log/?sort_dir=asc&limit=200', headers=auth_headers)
        actions = [l['action'] for l in resp.get_json()['data']
                   if l['action'] in ('zz_first_action', 'zz_second_action')]
        assert actions == ['zz_first_action', 'zz_second_action']


class TestLogFilterOptions:
    def test_usernames_requires_auth(self, client):
        assert client.get('/log/usernames').status_code == 401

    def test_usernames_returns_distinct_sorted(self, client, auth_headers, seed_admin):
        """auth_headers fixture 登入時本身就會留一筆 admin/login，所以結果裡
        一定含 'admin' —— 用集合包含關係檢查，不要求剛好等於兩人的清單。
        """
        Log.create('bob', 'act')
        Log.create('alice', 'act')
        Log.create('alice', 'act2')
        resp = client.get('/log/usernames', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data == sorted(data)
        assert {'alice', 'bob'} <= set(data)

    def test_usernames_includes_non_admin_sentinels(self, client, auth_headers, seed_admin):
        """要包含 unknown／player:xxx 這種非後台帳號的值，不能只列 User.find_all()。"""
        Log.create('unknown', 'login', success=False)
        Log.create('player:ABC123', 'issue_discord_code')
        resp = client.get('/log/usernames', headers=auth_headers)
        data = resp.get_json()['data']
        assert 'unknown' in data
        assert 'player:ABC123' in data

    def test_actions_returns_distinct_sorted(self, client, auth_headers, seed_admin):
        Log.create('admin', 'login')
        Log.create('admin', 'delete_player')
        Log.create('admin', 'login')
        resp = client.get('/log/actions', headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()['data'] == ['delete_player', 'login']
