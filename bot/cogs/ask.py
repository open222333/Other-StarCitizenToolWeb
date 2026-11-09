"""/ask —— 用 AI 回答公會資料的問題（誰有某物品／藍圖／船、某玩家有什麼、哪裡買得到）。

AI 供應商輪換、工具、紀錄、每人限流都在 src/ai/（後台「系統設定 › AI 問答」設定 key 與順序）。
AI 呼叫是同步的 httpx，丟到 thread 跑，不卡住機器人。
"""

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from bot.ui import COLOR_INFO, DISCLAIMER, base_embed, error_embed
from src.ai import ask as ai_ask
from src.ai.config import PROVIDERS

#: Discord embed 描述上限 4096 字，留一點空間
ANSWER_MAX = 3900


class Ask(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name='ask', description='用 AI 問公會資料：誰有某物品／藍圖／船、某玩家有什麼、哪裡買得到')
    @app_commands.describe(question='想問的問題，例如：誰有大力神 C2？')
    @app_commands.guild_only()
    async def ask(self, interaction: discord.Interaction, question: str) -> None:
        user_key = f'discord:{interaction.user.id}'
        try:
            await asyncio.to_thread(ai_ask.check_rate, user_key)
        except ai_ask.AskError as exc:
            await interaction.response.send_message(embed=error_embed(str(exc)), ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(ai_ask.ask, question, f'{user_key}:{interaction.user}', 'discord')
        except ai_ask.AskError as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))
            return
        answer = result['answer']
        if len(answer) > ANSWER_MAX:
            answer = answer[:ANSWER_MAX] + '\n…（太長，後面省略）'
        embed = base_embed('🤖 ' + (question if len(question) <= 200 else question[:200] + '…'),
                           color=COLOR_INFO, description=answer)
        provider = result['providers'][-1] if result['providers'] else ''
        label = PROVIDERS.get(provider, {}).get('label', provider)
        embed.set_footer(text=f'AI：{label} · 可能有誤，請以網站為準 · {DISCLAIMER}')
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ask(bot))
