"""Discord 呈現層的共用元件：embed 樣式、分頁按鈕、權限檢查。"""

import datetime as dt
from typing import Awaitable, Callable, Optional, Union

import discord

from src import WMS_OPERATOR_ROLE

# CIG 要求標示非官方，每個 embed 都帶著這行
DISCLAIMER = 'Unofficial Star Citizen fan tool · not affiliated with Cloud Imperium'

COLOR_OK = 0x2ECC71
COLOR_INFO = 0x3AA7DE
COLOR_WARN = 0xF1C40F
COLOR_ERROR = 0xE74C3C

PAGE_SIZE = 15


def base_embed(title: str, *, color: int = COLOR_INFO,
               description: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=DISCLAIMER)
    return embed


def error_embed(message: str) -> discord.Embed:
    return base_embed('⚠️ 無法完成', color=COLOR_ERROR, description=message)


def scu(value: float) -> str:
    """SCU 顯示：小量給有效位數，大量取整。"""
    if not value:
        return '0 SCU'
    if value < 1:
        return f'{value:.4g} SCU'
    if value < 100:
        return f'{value:,.2f} SCU'
    return f'{value:,.0f} SCU'


def uec(value) -> str:
    return f'{value:,.0f} aUEC' if value else '—'


def rel_time(value: Optional[dt.datetime]) -> str:
    """Discord 相對時間標記。DB 存的是 naive UTC，補上 tzinfo 才能算 timestamp。"""
    if not value:
        return '—'
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return f'<t:{int(value.timestamp())}:R>'


def loc_label(location: Optional[str], container: Optional[str]) -> str:
    if container:
        return f'{location} / {container}'
    return location or '—'


def owner_label(owner_type: str, player: Optional[str]) -> str:
    return '公會共享庫' if owner_type == 'guild' else f'{player} 個人庫'


def is_operator(member: Union[discord.Member, discord.User]) -> bool:
    """動公會共享庫的權限。沒設 WMS_OPERATOR_ROLE 就一律放行。"""
    if not WMS_OPERATOR_ROLE:
        return True
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.manage_guild:
        return True
    return any(
        role.name == WMS_OPERATOR_ROLE or str(role.id) == WMS_OPERATOR_ROLE
        for role in member.roles
    )


class Paginator(discord.ui.View):
    """上一頁 / 下一頁按鈕。

    render 是 async callable，收到 (offset, limit) 回傳 (embed, total)。
    只有原始呼叫者能操作，避免頻道裡互相亂按。
    """

    def __init__(self, render: Callable[[int, int], Awaitable[tuple]], *,
                 author_id: int, total: int, page_size: int = PAGE_SIZE,
                 timeout: float = 180) -> None:
        super().__init__(timeout=timeout)
        self.render = render
        self.author_id = author_id
        self.total = total
        self.page_size = page_size
        self.page = 0
        self._refresh_buttons()

    @property
    def last_page(self) -> int:
        return max(0, (self.total - 1) // self.page_size)

    def _refresh_buttons(self) -> None:
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= self.last_page
        if self.total <= self.page_size:
            self.clear_items()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                '這是別人的查詢結果，請自己下一次指令。', ephemeral=True)
            return False
        return True

    async def _go(self, interaction: discord.Interaction, page: int) -> None:
        self.page = max(0, min(page, self.last_page))
        embed, self.total = await self.render(self.page * self.page_size, self.page_size)
        self._refresh_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='◀ 上一頁', style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, _) -> None:
        await self._go(interaction, self.page - 1)

    @discord.ui.button(label='下一頁 ▶', style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, _) -> None:
        await self._go(interaction, self.page + 1)

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
