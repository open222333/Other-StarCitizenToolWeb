"""把 src/models 的同步 pymongo 呼叫包成 async。

專案的資料層是同步 pymongo（Flask 用），discord.py 是 async。這裡用
asyncio.to_thread 橋接，讓 bot 直接沿用 src/models/inventory.py 的邏輯，
不重新實作一份 —— 庫存邏輯只能有一個事實來源。

pymongo 呼叫都很短，丟到 thread pool 不會有問題；不要為了 async 改寫成 motor。
"""

import asyncio
from typing import Optional

from src import WMS_SCOPE_ID
from src.models.inventory import (OWNER_GUILD, OWNER_PLAYER, DiscordBinding, Inventory,
                                  InventoryLog, StockError, uscu_to_scu)
from src.models.item import CommodityMaster, ItemMaster, SyncRun, VehicleMaster
from src.mongo import ensure_indexes, get_db

__all__ = [
    'SCOPE_ID', 'OWNER_GUILD', 'OWNER_PLAYER', 'StockError', 'uscu_to_scu',
    'ping', 'init_indexes', 'search_items', 'get_item', 'resolve_item',
    'search_vehicles', 'resolve_vehicle', 'item_prices', 'list_stock',
    'find_item_locations', 'capacity', 'distinct_locations', 'adjust_stock',
    'move_stock', 'recent_log', 'recent_log_for_owner', 'item_names',
    'get_binding', 'bind_handle', 'unbind_handle',
    'require_handle', 'latest_sync', 'game_versions',
]

SCOPE_ID = WMS_SCOPE_ID


async def _run(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


# ─────────────────────────────────────────────────────────── 基礎

async def ping() -> None:
    await _run(lambda: get_db().command('ping'))


async def init_indexes() -> None:
    await _run(ensure_indexes)


# ─────────────────────────────────────────────────────────── 主檔

async def search_items(query: str, limit: int = 25) -> list:
    return await _run(ItemMaster.search, query, limit)


async def get_item(item_id: str) -> Optional[dict]:
    return await _run(ItemMaster.get, item_id)


async def resolve_item(value: str) -> dict:
    """解析不出來就拋 StockError（訊息會直接顯示給玩家）。"""
    item = await _run(ItemMaster.resolve, value)
    if not item:
        raise StockError(f'找不到物品「{value}」，或對到多筆。請用 autocomplete 選項。')
    return item


async def search_vehicles(query: str, limit: int = 25) -> list:
    return await _run(VehicleMaster.search, query, limit)


async def resolve_vehicle(value: str) -> Optional[dict]:
    return await _run(VehicleMaster.resolve, value)


async def item_prices(item: dict, limit: int = 10) -> list:
    return await _run(ItemMaster.prices, item, limit)


async def game_versions() -> list:
    return await _run(ItemMaster.game_versions)


async def latest_sync() -> Optional[dict]:
    return await _run(SyncRun.latest)


async def search_commodities(query: str, limit: int = 25) -> list:
    return await _run(CommodityMaster.search, query, limit)


# ─────────────────────────────────────────────────────────── 庫存查詢

async def list_stock(owner_type: str, player: Optional[str], location: str = '',
                     item_id: str = '', offset: int = 0, limit: int = 15) -> tuple:
    return await _run(Inventory.list_stock, SCOPE_ID, owner_type, player,
                      location, item_id, offset, limit)


async def find_item_locations(item_id: str) -> list:
    return await _run(Inventory.find_item_locations, SCOPE_ID, item_id)


async def capacity(owner_type: str, player: Optional[str], location: str = '') -> dict:
    return await _run(Inventory.capacity, SCOPE_ID, owner_type, player, location)


async def distinct_locations(limit: int = 200) -> list:
    return await _run(Inventory.distinct_locations, SCOPE_ID, limit)


async def recent_log(limit: int = 20) -> list:
    """整個 scope 的異動紀錄（含所有人的個人庫）。

    ⚠️ 這支沒有歸屬過濾，**不要直接拿去回給使用者** —— 那會把別人個人庫的
    品項、數量、地點全部外洩（bot 的 /history 曾經就是這樣）。
    要給人看的一律用 recent_log_for_owner()。
    """
    return await _run(InventoryLog.recent, SCOPE_ID, limit)


async def recent_log_for_owner(owner_type: str, player: Optional[str],
                               limit: int = 20) -> list:
    """指定歸屬的異動紀錄：公會庫（player=None）或某個人的個人庫。"""
    return await _run(InventoryLog.recent_for_owner, SCOPE_ID, owner_type, player, limit)


async def item_names(item_ids) -> dict:
    """`{uuid: 顯示名稱}` —— 一次 $in 批次查，不要逐筆 get_item()。"""
    names = await _run(ItemMaster.names_by_ids, list(item_ids))
    return {uuid: (info.get('name') or uuid) for uuid, info in names.items()}


# ─────────────────────────────────────────────────────────── 庫存異動

async def adjust_stock(owner_type: str, player: Optional[str], location: str,
                       container: Optional[str], item_id: str, delta: int,
                       actor: str, actor_id: str, note: str = '') -> dict:
    return await _run(Inventory.adjust, SCOPE_ID, owner_type, player, location,
                      container, item_id, delta, actor, actor_id, note)


async def move_stock(owner_type: str, player: Optional[str], item_id: str, quantity: int,
                     src_location: str, src_container: Optional[str],
                     dst_location: str, dst_container: Optional[str],
                     actor: str, actor_id: str) -> dict:
    return await _run(Inventory.move, SCOPE_ID, owner_type, player, item_id, quantity,
                      src_location, src_container, dst_location, dst_container,
                      actor, actor_id)


# ─────────────────────────────────────────────────────────── 綁定

async def get_binding(discord_id: str) -> Optional[dict]:
    return await _run(DiscordBinding.get, discord_id)


async def bind_handle(discord_id: str, handle: str, discord_name: str = '',
                      code: str = '') -> dict:
    """綁定需要玩家在網頁自助頁產生的綁定碼，見 DiscordBinding.bind()。"""
    return await _run(DiscordBinding.bind, discord_id, handle, SCOPE_ID,
                      discord_name, code)


async def unbind_handle(discord_id: str) -> bool:
    return await _run(DiscordBinding.unbind, discord_id)


async def require_handle(discord_id: str) -> str:
    return await _run(DiscordBinding.require_handle, discord_id)
