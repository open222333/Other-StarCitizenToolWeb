"""Discord bot 的健康檢查（docker-compose.bot.yml 的 healthcheck 跑 `python -m bot.health`）。

bot 連上 Discord 後每 HEARTBEAT_EVERY 秒寫一次心跳檔（bot/main.py 的 WmsBot._heartbeat）；
心跳檔超過 STALE_AFTER 秒沒更新（斷線沒重連、事件迴圈卡住）或根本沒有，就回報不健康。
這支只讀檔案，不載入 discord.py 和設定，跑起來很輕。
"""

import os
import sys
import time

HEARTBEAT_FILE = os.environ.get('BOT_HEARTBEAT_FILE', '/tmp/sc-bot-heartbeat')
HEARTBEAT_EVERY = 30
STALE_AFTER = 180


def beat(path: str = HEARTBEAT_FILE) -> None:
    with open(path, 'w') as fp:
        fp.write(str(int(time.time())))


def is_healthy(path: str = HEARTBEAT_FILE, now: float = None, stale_after: int = STALE_AFTER) -> bool:
    try:
        age = (now if now is not None else time.time()) - os.path.getmtime(path)
    except OSError:
        return False
    return age <= stale_after


if __name__ == '__main__':
    sys.exit(0 if is_healthy() else 1)
