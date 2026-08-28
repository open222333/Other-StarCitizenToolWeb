"""/price —— 查物品在哪買賣、多少錢。

資料來源優先序：
  1. uex_items_prices（需 UEX_API_TOKEN，較完整）
  2. item_master.raw.uex_prices（Wiki API 內嵌，沒 token 也有）
兩者都是社群眾包資料，與實際伺服器可能有落差。
"""

import discord
from discord import app_commands
from discord.ext import commands

from bot import db
from bot.completers import item_autocomplete
from bot.ui import COLOR_INFO, base_embed, scu, uec


class Prices(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name='price', description='查物品在哪裡買賣、價格多少')
    @app_commands.describe(item='物品（用 autocomplete 選）')
    @app_commands.autocomplete(item=item_autocomplete)
    @app_commands.guild_only()
    async def price(self, interaction: discord.Interaction, item: str) -> None:
        await interaction.response.defer()

        item_doc = await db.resolve_item(item)
        rows = await db.item_prices(item_doc, limit=10)

        embed = base_embed(f"💰 {item_doc['name']}", color=COLOR_INFO)
        embed.add_field(name='類型', value=f"`{item_doc.get('type') or '—'}`", inline=True)
        if item_doc.get('size'):
            embed.add_field(name='尺寸', value=f"S{item_doc['size']}", inline=True)
        embed.add_field(name='體積', value=scu(db.uscu_to_scu(item_doc.get('volume_uscu'))),
                        inline=True)

        if not rows:
            embed.description = ('沒有這個物品的價格資料。\n'
                                 '可能是任務／活動獎勵物品，或社群還沒回報。')
            await interaction.followup.send(embed=embed)
            return

        buys = [row for row in rows if row.get('price_buy')]
        sells = [row for row in rows if row.get('price_sell')]

        if buys:
            cheapest = min(buys, key=lambda r: r['price_buy'])
            embed.description = (f"最便宜：**{uec(cheapest['price_buy'])}** "
                                 f"@ {cheapest.get('terminal_name') or '未知終端'}")
            lines = [
                f"{uec(row['price_buy'])} · {row.get('terminal_name') or '未知終端'}"
                + (f" ({row['location']})" if row.get('location') else '')
                for row in sorted(buys, key=lambda r: r['price_buy'])[:8]
            ]
            embed.add_field(name='🛒 可購買', value='\n'.join(lines), inline=False)

        if sells:
            lines = [
                f"{uec(row['price_sell'])} · {row.get('terminal_name') or '未知終端'}"
                for row in sorted(sells, key=lambda r: -(r['price_sell'] or 0))[:5]
            ]
            embed.add_field(name='💵 可售出', value='\n'.join(lines), inline=False)

        note = {
            'uex': '資料來源：UEX Corp（社群眾包）',
            'wiki': '資料來源：Star Citizen Wiki API 內嵌的 UEX 價格'
                    '（資料較少，設定 UEX_API_TOKEN 可取得完整價格）',
        }.get(rows[0].get('source'), '')
        if rows[0].get('game_version'):
            note += f" · 遊戲版本 {rows[0]['game_version']}"
        if note:
            embed.add_field(name='​', value=note, inline=False)

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Prices(bot))
