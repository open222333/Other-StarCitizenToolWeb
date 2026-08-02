"""入出庫指令：/add /remove /move /history

權限：
  - 公會共享庫的異動需要 WMS_OPERATOR_ROLE 角色（環境變數留空 = 所有人都能動）。
    有 Manage Server 權限的人一律通過。
  - 個人庫永遠只有本人能動。

所有異動都經過 src/models/inventory.py 並寫入 inventory_log。
"""

from typing import Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot import db
from bot.completers import item_autocomplete, location_autocomplete
from bot.ui import COLOR_OK, base_embed, is_operator, loc_label, owner_label, rel_time, scu
from src import WMS_OPERATOR_ROLE
from src.models.inventory import StockError

Scope = Literal['公會共享庫', '我的個人庫']

# 單次異動上限，避免誤打一長串數字
MAX_QUANTITY = 1_000_000


class Stock(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _resolve_target(self, interaction: discord.Interaction,
                              scope: Scope) -> tuple:
        """回傳 (owner_type, player, actor_handle)，順便做權限檢查。"""
        actor = await db.require_handle(str(interaction.user.id))

        if scope == '我的個人庫':
            return db.OWNER_PLAYER, actor, actor

        if not is_operator(interaction.user):
            raise StockError(
                f'動公會共享庫需要 `{WMS_OPERATOR_ROLE}` 角色。'
                f'你可以改用 `scope: 我的個人庫`。')
        return db.OWNER_GUILD, None, actor

    # ─────────────────────────────────────────────────────── /add

    @app_commands.command(name='add', description='入庫')
    @app_commands.describe(item='物品（用 autocomplete 選）', quantity='數量',
                           location='放在哪（例如 Area18、Lorville）',
                           container='容器／箱號（可留空）',
                           scope='放進公會共享庫或個人庫', note='備註（可留空）')
    @app_commands.autocomplete(item=item_autocomplete, location=location_autocomplete)
    @app_commands.guild_only()
    async def add(self, interaction: discord.Interaction, item: str,
                  quantity: app_commands.Range[int, 1, MAX_QUANTITY],
                  location: str, container: Optional[str] = None,
                  scope: Scope = '公會共享庫', note: Optional[str] = None) -> None:
        await interaction.response.defer()

        owner_type, player, actor = await self._resolve_target(interaction, scope)
        item_doc = await db.resolve_item(item)

        doc = await db.adjust_stock(
            owner_type, player, location=location, container=container,
            item_id=item_doc['_id'], delta=quantity, actor=actor,
            actor_id=f'discord:{interaction.user.id}', note=note or '')

        unit_scu = db.uscu_to_scu(item_doc.get('volume_uscu'))
        embed = base_embed('✅ 入庫完成', color=COLOR_OK)
        embed.add_field(name='物品', value=item_doc['name'], inline=False)
        embed.add_field(name='數量',
                        value=f"+{quantity:,} → 現有 **{doc['quantity']:,}**", inline=True)
        embed.add_field(name='位置', value=loc_label(location, container), inline=True)
        embed.add_field(name='歸屬', value=owner_label(owner_type, player), inline=True)
        embed.add_field(name='體積',
                        value=f"本次 {scu(round(unit_scu * quantity, 4))}"
                              f" · 累計 {scu(round(unit_scu * doc['quantity'], 4))}",
                        inline=False)
        if note:
            embed.add_field(name='備註', value=note[:1024], inline=False)
        embed.set_author(name=f'操作者：{actor}')

        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────── /remove

    @app_commands.command(name='remove', description='出庫')
    @app_commands.describe(item='物品（用 autocomplete 選）', quantity='數量',
                           location='從哪裡出', container='容器／箱號（可留空）',
                           scope='從公會共享庫或個人庫出', note='備註（可留空）')
    @app_commands.autocomplete(item=item_autocomplete, location=location_autocomplete)
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, item: str,
                     quantity: app_commands.Range[int, 1, MAX_QUANTITY],
                     location: str, container: Optional[str] = None,
                     scope: Scope = '公會共享庫', note: Optional[str] = None) -> None:
        await interaction.response.defer()

        owner_type, player, actor = await self._resolve_target(interaction, scope)
        item_doc = await db.resolve_item(item)

        doc = await db.adjust_stock(
            owner_type, player, location=location, container=container,
            item_id=item_doc['_id'], delta=-quantity, actor=actor,
            actor_id=f'discord:{interaction.user.id}', note=note or '')

        embed = base_embed('✅ 出庫完成', color=COLOR_OK)
        embed.add_field(name='物品', value=item_doc['name'], inline=False)
        embed.add_field(name='數量',
                        value=f"−{quantity:,} → 剩下 **{doc['quantity']:,}**", inline=True)
        embed.add_field(name='位置', value=loc_label(location, container), inline=True)
        embed.add_field(name='歸屬', value=owner_label(owner_type, player), inline=True)
        if doc['quantity'] == 0:
            embed.description = '這個位置的該物品已清空。'
        if note:
            embed.add_field(name='備註', value=note[:1024], inline=False)
        embed.set_author(name=f'操作者：{actor}')

        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────── /move

    @app_commands.command(name='move', description='把庫存從一個位置移到另一個位置')
    @app_commands.describe(item='物品（用 autocomplete 選）', quantity='數量',
                           source='來源位置', destination='目的位置',
                           source_container='來源容器（可留空）',
                           destination_container='目的容器（可留空）',
                           scope='公會共享庫或個人庫')
    @app_commands.autocomplete(item=item_autocomplete, source=location_autocomplete,
                               destination=location_autocomplete)
    @app_commands.guild_only()
    async def move(self, interaction: discord.Interaction, item: str,
                   quantity: app_commands.Range[int, 1, MAX_QUANTITY],
                   source: str, destination: str,
                   source_container: Optional[str] = None,
                   destination_container: Optional[str] = None,
                   scope: Scope = '公會共享庫') -> None:
        await interaction.response.defer()

        owner_type, player, actor = await self._resolve_target(interaction, scope)
        item_doc = await db.resolve_item(item)

        result = await db.move_stock(
            owner_type, player, item_id=item_doc['_id'], quantity=quantity,
            src_location=source, src_container=source_container,
            dst_location=destination, dst_container=destination_container,
            actor=actor, actor_id=f'discord:{interaction.user.id}')

        embed = base_embed('✅ 移庫完成', color=COLOR_OK)
        embed.add_field(name='物品', value=f"{item_doc['name']} × {quantity:,}", inline=False)
        embed.add_field(
            name='來源',
            value=f"{loc_label(source, source_container)}\n"
                  f"剩 **{result['src']['quantity']:,}**", inline=True)
        embed.add_field(
            name='目的',
            value=f"{loc_label(destination, destination_container)}\n"
                  f"現有 **{result['dst']['quantity']:,}**", inline=True)
        embed.add_field(name='歸屬', value=owner_label(owner_type, player), inline=True)
        embed.set_author(name=f'操作者：{actor}')

        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────── /history

    @app_commands.command(name='history', description='最近的庫存異動紀錄')
    @app_commands.describe(limit='要看幾筆（1～25）')
    @app_commands.guild_only()
    async def history(self, interaction: discord.Interaction,
                      limit: app_commands.Range[int, 1, 25] = 10) -> None:
        await interaction.response.defer()

        rows = await db.recent_log(limit=limit)
        embed = base_embed('🧾 最近異動')

        if not rows:
            embed.description = '還沒有任何異動紀錄。'
            await interaction.followup.send(embed=embed)
            return

        icons = {'add': '📥', 'remove': '📤', 'move': '🔀', 'move_rollback_failed': '🚨'}
        names: dict = {}
        lines = []

        for row in rows:
            item_id = row.get('item_id', '')
            if item_id not in names:
                item = await db.get_item(item_id)
                names[item_id] = (item or {}).get('name') or item_id
            lines.append(
                f"{icons.get(row.get('action'), '•')} **{names[item_id]}** "
                f"{row.get('delta', 0):+,} → {row.get('quantity_after', 0):,}\n"
                f"　{loc_label(row.get('location'), row.get('container'))}"
                f" · {row.get('actor') or '?'} · {rel_time(row.get('ts'))}")

        embed.description = '\n'.join(lines)
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stock(bot))
