"""斜線指令的 autocomplete。

回傳的 value 一律是遊戲 uuid，這樣指令拿到的就是明確主鍵，不用猜使用者打的名字。
Discord 限制最多 25 個選項、name 最長 100 字。
"""

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
            name=_label(row['name'],
                        f"{row['cargo_capacity_scu']} SCU"
                        if row.get('cargo_capacity_scu') else None),
            value=row['_id'],
        )
        for row in rows
    ]


async def location_autocomplete(interaction: discord.Interaction,
                                current: str) -> list:
    """位置是自由文字，這裡只把用過的位置列出來方便選。"""
    locations = await db.distinct_locations(limit=200)
    needle = (current or '').strip().lower()
    if needle:
        locations = [loc for loc in locations if needle in loc.lower()]
    return [
        app_commands.Choice(name=loc[:MAX_LABEL], value=loc[:MAX_LABEL])
        for loc in locations[:MAX_CHOICES]
    ]
