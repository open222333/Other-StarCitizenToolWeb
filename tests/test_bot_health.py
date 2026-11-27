"""bot 健康檢查：心跳檔太舊或不存在就不健康（bot/health.py）。"""
import os

from bot import health


def test_heartbeat_fresh_and_stale(tmp_path):
    path = str(tmp_path / 'hb')
    assert health.is_healthy(path) is False                       # 還沒寫過
    health.beat(path)
    mtime = os.path.getmtime(path)
    assert health.is_healthy(path, now=mtime + 60) is True
    assert health.is_healthy(path, now=mtime + health.STALE_AFTER + 1) is False
