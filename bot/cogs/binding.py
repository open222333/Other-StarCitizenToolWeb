"""/bind /unbind /whoami —— Discord 帳號與 RSI handle 的自助綁定。"""

import discord
from discord import app_commands
from discord.ext import commands

from bot import db
from bot.ui import COLOR_OK, base_embed, rel_time


class Binding(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name='bind', description='綁定你的 RSI handle，之後才能操作個人庫存')
    @app_commands.describe(
        handle='你的 RSI handle（遊戲內名稱，大小寫要跟網頁上一致）',
        code='玩家網頁「我的資料 → 產生 Discord 綁定碼」給的 8 碼（10 分鐘內有效）',
    )
    @app_commands.guild_only()
    async def bind(self, interaction: discord.Interaction, handle: str, code: str) -> None:
        """綁定需要綁定碼 —— Discord 帳號無法自己證明它屬於哪個遊戲帳號，
        沒有這道驗證的話，任何人打 `/bind handle:別人的ID` 就能讀寫、
        甚至清空別人的個人庫存。碼由需要密碼登入的網頁產生。"""
        existing = await db.get_binding(str(interaction.user.id))
        doc = await db.bind_handle(str(interaction.user.id), handle,
                                   discord_name=interaction.user.name, code=code)

        verb = '已更新綁定' if existing else '綁定完成'
        embed = base_embed(f'✅ {verb}', color=COLOR_OK)
        embed.add_field(name='Discord', value=interaction.user.mention, inline=True)
        embed.add_field(name='RSI handle', value=f"`{doc['handle']}`", inline=True)

        if existing and existing['handle'] != doc['handle']:
            embed.add_field(name='原本綁定', value=f"`{existing['handle']}`", inline=False)
            embed.description = ('注意：既有庫存紀錄掛在舊 handle 底下，'
                                 '改名後查不到舊資料。需要搬移請找管理員。')

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='unbind', description='解除 RSI handle 綁定')
    @app_commands.guild_only()
    async def unbind(self, interaction: discord.Interaction) -> None:
        removed = await db.unbind_handle(str(interaction.user.id))
        message = ('已解除綁定。庫存紀錄仍保留 —— 重新綁定需要再去玩家網頁的'
                   '「我的資料」產生一組綁定碼。'
                   if removed else '你本來就沒有綁定。')
        await interaction.response.send_message(
            embed=base_embed('綁定狀態', description=message), ephemeral=True)

    @app_commands.command(name='whoami', description='查看目前的綁定狀態與資料同步時間')
    @app_commands.guild_only()
    async def whoami(self, interaction: discord.Interaction) -> None:
        binding = await db.get_binding(str(interaction.user.id))
        embed = base_embed('你的綁定')

        if binding:
            embed.add_field(name='RSI handle', value=f"`{binding['handle']}`", inline=True)
            embed.add_field(name='綁定時間', value=rel_time(binding.get('created_at')),
                            inline=True)
        else:
            embed.description = ('尚未綁定。先到玩家網頁的「我的資料」按'
                                '「產生 Discord 綁定碼」，再用 '
                                '`/bind handle:<你的遊戲ID> code:<綁定碼>`。')

        run = await db.latest_sync()
        if run:
            status = '正常' if run.get('ok') else f"有 {len(run.get('errors') or [])} 個錯誤"
            embed.add_field(name='遊戲主檔同步',
                            value=f"{rel_time(run.get('finished_at'))} · {status}",
                            inline=False)

        versions = await db.game_versions()
        if versions:
            embed.add_field(name='遊戲版本', value=', '.join(versions[-2:]), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Binding(bot))
