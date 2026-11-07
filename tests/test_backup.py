"""後台資料備份（src/backup.py、/data/backup/*）：匯出→還原要原樣回來，檔案不對要擋。"""
import gzip
import io
import json

import pytest

from src import backup
from src.mongo import get_db


@pytest.fixture
def seed(app):
    db = get_db()
    db['players'].insert_many([{'star_citizen_id': 'TomLi', 'nickname': '湯姆'}, {'star_citizen_id': 'Amy'}])
    db['fleet'].insert_one({'player_id': 'x', 'name': 'C2', 'quantity': 2})
    db['logs'].insert_one({'username': 'admin', 'action': 'x'})
    yield db


def test_export_then_restore_roundtrip(seed):
    raw = backup.export_gzip(['players', 'player_data'])
    data = json.loads(gzip.decompress(raw))
    assert data['format'] == backup.BACKUP_FORMAT
    assert 'logs' not in data['collections']           # 沒選的不匯出
    # 改掉原本的資料，再從備份還原
    seed['players'].delete_many({})
    seed['players'].insert_one({'star_citizen_id': 'Other'})
    counts = backup.restore(backup.load_file(raw), ['players'])
    assert counts['players'] == 2
    assert {p['star_citizen_id'] for p in seed['players'].find()} == {'TomLi', 'Amy'}
    assert seed['fleet'].count_documents({}) == 1        # 沒選還原的不動


def test_restore_keeps_object_ids(seed):
    ids = {p['_id'] for p in seed['players'].find()}
    raw = backup.export_gzip(['players'])
    seed['players'].delete_many({})
    backup.restore(backup.load_file(raw), ['players'])
    assert {p['_id'] for p in seed['players'].find()} == ids


def test_rejects_foreign_file():
    with pytest.raises(backup.BackupError):
        backup.load_file(json.dumps({'hello': 1}).encode())


def test_rejects_set_missing_from_file(seed):
    raw = backup.export_gzip(['players'])
    with pytest.raises(backup.BackupError):
        backup.restore(backup.load_file(raw), ['tool_links'])


def test_accounts_restore_requires_current_admin(app):
    db = get_db()
    db['users'].insert_one({'username': 'someone'})
    raw = backup.export_gzip(['accounts'])
    with pytest.raises(backup.BackupError):
        backup.restore(backup.load_file(raw), ['accounts'], keep_username='admin')


def test_api_export_and_dry_run(client, auth_headers, seed):
    res = client.get('/data/backup/export?set=players', headers=auth_headers)
    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.headers['Content-Type'].startswith('application/gzip')
    headers = {k: v for k, v in auth_headers.items() if k.lower() != 'content-type'}
    res2 = client.post('/data/backup/import', headers=headers, content_type='multipart/form-data',
                       data={'file': (io.BytesIO(res.data), 'b.json.gz'), 'dry_run': '1'})
    assert res2.status_code == 200, res2.get_data(as_text=True)
    sets = res2.get_json()['data']['sets']
    assert sets[0]['key'] == 'players' and sets[0]['collections'][0]['count'] == 2


def test_api_requires_admin(client):
    assert client.get('/data/backup/sets').status_code in (401, 422)
