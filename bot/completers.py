"""斜線指令的 autocomplete。

回傳的 value 一律是遊戲 uuid，這樣指令拿到的就是明確主鍵，不用猜使用者打的名字。
Discord 限制最多 25 個選項、name 最長 100 字。
"""

import time

import discord
from discord import app_commands

from bot import db

MAX_CHOICES = 25
MAX_LABEL = 100


def _label(*parts) -> str:
    text = ' · '.join(str(p) for p in parts if p not in (None, '', 'UNDEFINED'))
    return text[:MAX_LABEL]


async def item_autocomplete(interaction: discord.Interaction,
                            current: str) -> list:
    rows = await db.search_items(current, limit=MAX_CHOICES)
    return [
        app_commands.Choice(
            name=_label(row['name'], row.get('type'),
                        f"S{row['size']}" if row.get('size') else None),
            value=row['_id'],
        )
        for row in rows
    ]


async def vehicle_autocomplete(interaction: discord.Interaction,
                               current: str) -> list:
    rows = await db.search_vehicles(current, limit=MAX_CHOICES)
    return [
        app_commands.Choice(
            # 同名變體帶上系統說明（例如 [Plat]），不然選單上看起來一模一樣
            name=_label(f"{row['name']} [{row['system_note']}]" if row.get('system_note') else row['name'],
                        f"{row['cargo_capacity_scu']} SCU"
                        if row.get('cargo_capacity_scu') else None),
            value=row['_id'],
        )
        for row in rows
    ]


# 位置清單的短期快取。
#
# autocomplete 是**每一個按鍵**都會觸發的：打「Area18」就是 7 次
# distinct_locations()，而那支要掃 inventory 做 distinct。位置清單幾乎不變
# （有人入庫到新地點才會多一個），所以快取 60 秒完全夠用，
# 換來的是打字時不再每個字元都打一次 DB。
_LOCATION_CACHE: dict = {'at': 0.0, 'rows': []}
_LOCATION_TTL_S = 60


async def _cached_locations() -> list:
    now = time.monotonic()
    if _LOCATION_CACHE['rows'] and now - _LOCATION_CACHE['at'] < _LOCATION_TTL_S:
        return _LOCATION_CACHE['rows']
    used = await db.distinct_locations(limit=200)
    # 用過的地點排前面，再補地點資料庫裡「可存放」的地點（還沒有人登記過也能選）
    try:
        storage = await db.storage_location_names()
    except Exception:
        storage = []
    seen = {loc.lower() for loc in used}
    rows = used + [n for n in storage if n.lower() not in seen]
    _LOCATION_CACHE.update(at=now, rows=rows)
    return rows


async def location_autocomplete(interaction: discord.Interaction,
                                current: str) -> list:
    """位置是自由文字，這裡列出用過的位置＋可存放的地點方便選。"""
    locations = await _cached_locations()
    needle = (current or '').strip().lower()
    if needle:
        locations = [loc for loc in locations if needle in loc.lower()]
    return [
        app_commands.Choice(name=loc[:MAX_LABEL], value=loc[:MAX_LABEL])
        for loc in locations[:MAX_CHOICES]
    ]
