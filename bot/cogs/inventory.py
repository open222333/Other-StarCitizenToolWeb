"""查詢類指令：/stock /find /where /capacity

個人庫的回覆一律 ephemeral（只有自己看得到），公會庫查詢公開。
"""

from typing import Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot import db
from bot.completers import item_autocomplete, location_autocomplete, vehicle_autocomplete
from bot.ui import (COLOR_INFO, COLOR_OK, COLOR_WARN, PAGE_SIZE, Paginator, base_embed,
                    loc_label, owner_label, rel_time, scu)

Scope = Literal['公會共享庫', '我的個人庫']


class Inventory(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _resolve_scope(self, interaction: discord.Interaction,
                             scope: Scope) -> tuple:
        """回傳 (owner_type, player, is_personal)。個人庫需要先綁定。"""
        if scope == '我的個人庫':
            handle = await db.require_handle(str(interaction.user.id))
            return db.OWNER_PLAYER, handle, True
        return db.OWNER_GUILD, None, False

    # ─────────────────────────────────────────────────────── /stock

    @app_commands.command(name='stock', description='查庫存（預設查公會共享庫）')
    @app_commands.describe(scope='要查公會共享庫還是自己的個人庫',
                           location='只看某個位置（可留空）',
                           item='只看某個物品（可留空）')
    @app_commands.autocomplete(location=location_autocomplete, item=item_autocomplete)
    @app_commands.guild_only()
    async def stock(self, interaction: discord.Interaction,
                    scope: Scope = '公會共享庫',
                    location: Optional[str] = None,
                    item: Optional[str] = None) -> None:
        owner_type, player, is_personal = await self._resolve_scope(interaction, scope)

        item_doc = await db.resolve_item(item) if item else None
        item_id = item_doc['_id'] if item_doc else ''

        await interaction.response.defer(ephemeral=is_personal)

        async def render(offset: int, limit: int) -> tuple:
            rows, total = await db.list_stock(
                owner_type, player, location=location or '',
                item_id=item_id, offset=offset, limit=limit)
            summary = await db.capacity(owner_type, player, location=location or '')

            title = f'📦 {owner_label(owner_type, player)}'
            if location:
                title += f' · {location}'
            embed = base_embed(title, color=COLOR_INFO)

            if total == 0:
                embed.description = '這裡沒有庫存。用 `/add` 入庫。'
                return embed, total

            lines = []
            for row in rows:
                flag = ' ⚠️' if row.get('item_retired') else ''
                lines.append(
                    f"**{row['item_name']}**{flag} × {row['quantity']:,}\n"
                    f"　{loc_label(row.get('location'), row.get('container'))}"
                    f" · {scu(row.get('total_scu'))}")
            embed.description = '\n'.join(lines)

            page_no = offset // limit + 1
            pages = max(1, -(-total // limit))
            embed.add_field(name='品項', value=f"{total:,} 項", inline=True)
            embed.add_field(name='總量', value=f"{summary['units']:,} 個", inline=True)
            embed.add_field(name='佔用體積', value=scu(summary['total_scu']), inline=True)

            notes = [f'第 {page_no}/{pages} 頁']
            if summary['unknown_volume']:
                notes.append(f"{summary['unknown_volume']} 項缺體積資料，總量為低估")
            if any(row.get('item_retired') for row in rows):
                notes.append('⚠️ = 該物品已在目前遊戲版本移除')
            embed.add_field(name='​', value='　'.join(notes), inline=False)

            return embed, total

        embed, total = await render(0, PAGE_SIZE)
        view = (Paginator(render, author_id=interaction.user.id, total=total)
                if total > PAGE_SIZE else discord.utils.MISSING)
        await interaction.followup.send(embed=embed, view=view)

    # ─────────────────────────────────────────────────────── /find

    @app_commands.command(name='find', description='搜尋物品主檔（遊戲裡有哪些物品，不是庫存）')
    @app_commands.describe(query='物品名稱或 class name 的一部分')
    @app_commands.guild_only()
    async def find(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()

        rows = await db.search_items(query, limit=15)
        embed = base_embed(f'🔍 搜尋「{query}」', color=COLOR_INFO)

        if not rows:
            embed.description = '找不到符合的物品。'
            await interaction.followup.send(embed=embed)
            return

        for row in rows[:10]:
            details = [
                f"類型 `{row.get('type') or '—'}`",
                f"尺寸 S{row['size']}" if row.get('size') else None,
                f"體積 {scu(db.uscu_to_scu(row.get('volume_uscu')))}",
                f"製造商 {row.get('manufacturer_code') or '—'}",
            ]
            embed.add_field(
                name=row['name'][:256],
                value='　'.join(d for d in details if d) + f"\n`{row['_id']}`",
                inline=False)

        if len(rows) > 10:
            embed.set_footer(text=f'還有 {len(rows) - 10} 筆未顯示，請縮小關鍵字')
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────── /where

    @app_commands.command(name='where', description='查某個物品在公會範圍內都放在哪些位置')
    @app_commands.describe(item='物品（用 autocomplete 選）')
    @app_commands.autocomplete(item=item_autocomplete)
    @app_commands.guild_only()
    async def where(self, interaction: discord.Interaction, item: str) -> None:
        await interaction.response.defer()

        item_doc = await db.resolve_item(item)
        rows = await db.find_item_locations(item_doc['_id'])

        embed = base_embed(f"📍 {item_doc['name']}", color=COLOR_INFO)
        if not rows:
            embed.description = '公會範圍內沒有這個物品的庫存。'
            await interaction.followup.send(embed=embed)
            return

        total = sum(row['quantity'] for row in rows)
        unit_scu = db.uscu_to_scu(item_doc.get('volume_uscu'))

        embed.description = '\n'.join(
            f"**{loc_label(row.get('location'), row.get('container'))}** × {row['quantity']:,}\n"
            f"　{owner_label(row['owner_type'], row.get('player'))}"
            f" · 更新 {rel_time(row.get('updated_at'))}"
            for row in rows[:15])

        embed.add_field(name='總數', value=f'{total:,} 個', inline=True)
        embed.add_field(name='單位體積', value=scu(unit_scu), inline=True)
        embed.add_field(name='總體積', value=scu(round(unit_scu * total, 4)), inline=True)
        if len(rows) > 15:
            embed.add_field(name='​', value=f'另有 {len(rows) - 15} 個位置未顯示',
                            inline=False)

        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────── /capacity

    @app_commands.command(name='capacity',
                         description='算某個位置佔用多少 SCU，可比對船艙裝不裝得下')
    @app_commands.describe(location='要計算的位置（留空就是全部）',
                           scope='公會共享庫或個人庫',
                           ship='拿哪艘船來比對容量（可留空）')
    @app_commands.autocomplete(location=location_autocomplete, ship=vehicle_autocomplete)
    @app_commands.guild_only()
    async def capacity(self, interaction: discord.Interaction,
                       location: Optional[str] = None,
                       scope: Scope = '公會共享庫',
                       ship: Optional[str] = None) -> None:
        owner_type, player, is_personal = await self._resolve_scope(interaction, scope)
        await interaction.response.defer(ephemeral=is_personal)

        summary = await db.capacity(owner_type, player, location=location or '')

        title = f'📐 {owner_label(owner_type, player)}'
        if location:
            title += f' · {location}'
        embed = base_embed(title, color=COLOR_INFO)
        embed.add_field(name='品項', value=f"{summary['lines']:,} 項", inline=True)
        embed.add_field(name='總量', value=f"{summary['units']:,} 個", inline=True)
        embed.add_field(name='佔用體積', value=scu(summary['total_scu']), inline=True)

        if summary['unknown_volume']:
            embed.add_field(
                name='⚠️ 注意',
                value=f"有 {summary['unknown_volume']} 項物品在主檔裡沒有體積資料，"
                      f'實際佔用會比上面的數字大。',
                inline=False)

        if ship:
            vehicle = await db.resolve_vehicle(ship)
            if not vehicle:
                embed.add_field(name='船艙比對', value=f'找不到載具 `{ship}`', inline=False)
            else:
                cargo = vehicle.get('cargo_capacity_scu') or 0
                inventory_scu = db.uscu_to_scu(vehicle.get('vehicle_inventory_uscu'))
                needed = summary['total_scu']

                if cargo <= 0:
                    verdict = (f'這艘船沒有標準貨艙（僅隨身置物空間 {scu(inventory_scu)}），'
                               f'裝不下 {scu(needed)}。')
                    color = COLOR_WARN
                elif needed <= cargo:
                    verdict = (f'裝得下 ✅　使用 {scu(needed)} / {cargo:,} SCU '
                               f'（{needed / cargo * 100:.0f}%），剩 {scu(cargo - needed)}')
                    color = COLOR_OK
                else:
                    trips = int(-(-needed // cargo))
                    verdict = (f'裝不下 ❌　需要 {scu(needed)}，貨艙只有 {cargo:,} SCU。'
                               f'要跑 {trips} 趟。')
                    color = COLOR_WARN

                embed.color = color
                embed.add_field(name=f"🚀 {vehicle['name']}", value=verdict, inline=False)

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Inventory(bot))
