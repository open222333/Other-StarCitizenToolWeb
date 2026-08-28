#!/usr/bin/env python3
"""SC WMS Discord bot —— 在 Discord 用斜線指令查改倉庫庫存。

啟動（專案根目錄）：
    python -m bot.main

指令一覽：
  /bind      綁定 RSI handle          /unbind  解除綁定       /whoami  看目前綁定
  /stock     查庫存                   /find    搜物品主檔     /where   查物品在哪
  /capacity  算佔用 SCU（可比對船艙）  /price   查 UEX 價格
  /add       入庫                     /remove  出庫           /move    移庫
  /history   最近異動紀錄

庫存邏輯共用 src/models/inventory.py，與 Web API 同一份資料（WMS_SCOPE_ID 決定範圍）。

Unofficial Star Citizen fan tool. Not affiliated with the Cloud Imperium group of companies.
"""

import asyncio
import logging
import sys

import discord
from discord import app_commands
from discord.ext import commands

from bot import db
from bot.ui import error_embed
from src import DISCORD_GUILD_ID, DISCORD_TOKEN, LOG_LEVEL, WMS_SCOPE_ID
from src.models.inventory import StockError

COGS = ('bot.cogs.binding', 'bot.cogs.inventory', 'bot.cogs.stock', 'bot.cogs.prices')

log = logging.getLogger('sc-bot')


class WmsBot(commands.Bot):
    def __init__(self) -> None:
        # 只用斜線指令，不需要讀訊息內容，intents 保持最小
        super().__init__(command_prefix='!sc-unused', intents=discord.Intents.default())

    async def setup_hook(self) -> None:
        await db.ping()
        await db.init_indexes()
        log.info('MongoDB 連線正常，庫存範圍 WMS_SCOPE_ID=%s', WMS_SCOPE_ID)

        for cog in COGS:
            await self.load_extension(cog)
            log.info('載入 %s', cog)

        if DISCORD_GUILD_ID:
            # 指定 guild 的指令立即生效，開發時用這個
            guild = discord.Object(id=int(DISCORD_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info('已同步 %d 個指令到 guild %s', len(synced), DISCORD_GUILD_ID)
        else:
            # 全域指令要等 Discord 傳播，最多約一小時
            synced = await self.tree.sync()
            log.info('已同步 %d 個全域指令（傳播可能需要一段時間）', len(synced))

    async def on_ready(self) -> None:
        log.info('已登入為 %s (id=%s)', self.user, getattr(self.user, 'id', '?'))
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching, name='星際公民倉庫'))


async def on_app_command_error(interaction: discord.Interaction,
                               error: app_commands.AppCommandError) -> None:
    """StockError 是預期錯誤，訊息直接顯示；其他記 log 並回通用訊息。"""
    original = getattr(error, 'original', error)

    if isinstance(original, StockError):
        embed = error_embed(str(original))
    elif isinstance(error, app_commands.CommandOnCooldown):
        embed = error_embed(f'指令冷卻中，請 {error.retry_after:.0f} 秒後再試。')
    elif isinstance(error, app_commands.MissingPermissions):
        embed = error_embed('你沒有執行這個指令的權限。')
    else:
        log.exception('指令 %s 發生未預期錯誤',
                      getattr(interaction.command, 'name', '?'), exc_info=original)
        embed = error_embed('發生未預期的錯誤，已記錄到伺服器日誌。')

    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException:
        log.warning('無法回覆錯誤訊息給使用者')


async def main() -> int:
    logging.basicConfig(
        level=LOG_LEVEL.upper(),
        format='%(asctime)s %(levelname)-7s %(name)s: %(message)s',
        stream=sys.stdout,
    )

    if not DISCORD_TOKEN:
        log.error('沒有設定 DISCORD_TOKEN。到 '
                  'https://discord.com/developers/applications 建 application '
                  '→ Bot → Reset Token，填入 .env')
        return 1

    bot = WmsBot()
    bot.tree.on_error = on_app_command_error

    async with bot:
        await bot.start(DISCORD_TOKEN)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
