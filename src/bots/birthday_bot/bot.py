"""Birthday bot — stores birthdays and wishes people on the day."""

import calendar
import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from src.shared.database import Database

from . import queries

log = logging.getLogger(__name__)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
BIRTHDAY_COLOR = discord.Color.from_rgb(255, 105, 180)
FRAME = "🎈🎉🎊🎁🎂🎁🎊🎉🎈"

DB_OFFLINE = "❌ Database của Birthday bot đang không kết nối được."
GUILD_ONLY = "❌ Lệnh này chạy trong server, không chạy trong DM."
INVALID_DATE = "❌ Ngày `{day}/{month}` không có thật. Kiểm tra lại giùm nhé."
NO_BIRTHDAYS = "Chưa có ai trong danh sách. Dùng `/birthday-add` để thêm nhé 🎂"
MONTH_NAMES = [f"Tháng {m}" for m in range(1, 13)]


def _today() -> date:
    return datetime.now(VN_TZ).date()


def _next_occurrence(day: int, month: int, today: date) -> date:
    """Next date (today included) this birthday is celebrated.

    29/02 is celebrated on 28/02 in non-leap years.
    """
    for year in (today.year, today.year + 1):
        d = day
        if month == 2 and day == 29 and not calendar.isleap(year):
            d = 28
        candidate = date(year, month, d)
        if candidate >= today:
            return candidate
    raise AssertionError("unreachable")


def _celebrated_today(today: date) -> list[tuple[int, int]]:
    """(day, month) pairs whose birthday is celebrated today."""
    dates = [(today.day, today.month)]
    if today.month == 2 and today.day == 28 and not calendar.isleap(today.year):
        dates.append((29, 2))
    return dates


def _join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " và " + names[-1]


def build_birthday_embed(rows, today: date) -> discord.Embed:
    mentions = _join_names([f"<@{r['discord_id']}>" for r in rows])
    lines = [
        FRAME,
        "",
        f"Hôm nay là ngày sinh nhật của {mentions}, cùng chúc mọi điều "
        "tốt đẹp nhất dành cho bạn.",
        "",
        "🌸 Tuổi mới thật nhiều sức khoẻ, niềm vui và thành công nhé! 🌸",
        "",
        FRAME,
    ]

    embed = discord.Embed(
        title="🎂✨ CHÚC MỪNG SINH NHẬT ✨🎂",
        description="\n".join(lines),
        color=BIRTHDAY_COLOR,
    )
    embed.set_footer(text=f"📅 {today.strftime('%d/%m/%Y')}")
    return embed


class BirthdayBot:
    """Holds the bot wiring. One instance per bot process."""

    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
        self._register_commands()

    # ------------------------------------------------------------------ #
    #  Slash commands                                                      #
    # ------------------------------------------------------------------ #

    def _register_commands(self) -> None:
        @app_commands.command(
            name="birthday-add", description="Thêm (hoặc sửa) ngày sinh nhật"
        )
        @app_commands.describe(
            day="Ngày (1-31)",
            month="Tháng (1-12)",
            user="Sinh nhật của ai (mặc định: chính bạn)",
        )
        async def birthday_add(
            interaction: discord.Interaction,
            day: app_commands.Range[int, 1, 31],
            month: app_commands.Range[int, 1, 12],
            user: Optional[discord.Member] = None,
        ):
            await self._do_add(interaction, day, month, user)

        self.bot.tree.add_command(birthday_add)

        @app_commands.command(
            name="birthday-list", description="Xem danh sách sinh nhật"
        )
        async def birthday_list(interaction: discord.Interaction):
            await self._do_list(interaction)

        self.bot.tree.add_command(birthday_list)

        @app_commands.command(
            name="birthday-remove", description="Xoá ngày sinh nhật khỏi danh sách"
        )
        @app_commands.describe(user="Xoá của ai (mặc định: chính bạn)")
        async def birthday_remove(
            interaction: discord.Interaction,
            user: Optional[discord.Member] = None,
        ):
            await self._do_remove(interaction, user)

        self.bot.tree.add_command(birthday_remove)

        @app_commands.command(
            name="birthday-preview",
            description="Xem trước lời chúc sinh nhật (chỉ mình bạn thấy)",
        )
        async def birthday_preview(interaction: discord.Interaction):
            row = {"discord_id": interaction.user.id}
            await interaction.response.send_message(
                embed=build_birthday_embed([row], _today()), ephemeral=True
            )

        self.bot.tree.add_command(birthday_preview)

    async def _precheck(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id is None:
            await interaction.response.send_message(GUILD_ONLY, ephemeral=True)
            return False
        if not self.db.ready:
            await interaction.response.send_message(DB_OFFLINE, ephemeral=True)
            return False
        return True

    async def _do_add(
        self,
        interaction: discord.Interaction,
        day: int,
        month: int,
        user: Optional[discord.Member],
    ) -> None:
        if not await self._precheck(interaction):
            return

        # 2000 is a leap year, so 29/02 passes and 31/04 does not.
        try:
            date(2000, month, day)
        except ValueError:
            await interaction.response.send_message(
                INVALID_DATE.format(day=day, month=month), ephemeral=True
            )
            return

        target = user or interaction.user
        is_new = await queries.upsert_birthday(
            self.db,
            interaction.guild_id,
            target.id,
            day,
            month,
            interaction.user.id,
        )

        today = _today()
        date_str = f"{day:02d}/{month:02d}"
        days_left = (_next_occurrence(day, month, today) - today).days
        countdown = "🎉 Chính là hôm nay!" if days_left == 0 else f"⏳ Còn **{days_left}** ngày nữa."
        verb = "Đã thêm" if is_new else "Đã cập nhật"
        await interaction.response.send_message(
            f"🎂 {verb} sinh nhật của {target.mention}: **{date_str}**\n{countdown}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _do_list(self, interaction: discord.Interaction) -> None:
        if not await self._precheck(interaction):
            return

        rows = await queries.list_birthdays(self.db, interaction.guild_id)
        if not rows:
            await interaction.response.send_message(NO_BIRTHDAYS)
            return

        today = _today()
        by_month: dict[int, list[str]] = {}
        for r in rows:
            mark = " 🎉 **hôm nay**" if _next_occurrence(r["day"], r["month"], today) == today else ""
            by_month.setdefault(r["month"], []).append(
                f"`{r['day']:02d}/{r['month']:02d}` <@{r['discord_id']}>{mark}"
            )

        upcoming = min(rows, key=lambda r: _next_occurrence(r["day"], r["month"], today))
        next_date = _next_occurrence(upcoming["day"], upcoming["month"], today)
        days_left = (next_date - today).days
        when = "hôm nay 🎉" if days_left == 0 else f"còn **{days_left}** ngày"

        embed = discord.Embed(
            title="🎂 Danh sách sinh nhật",
            description=f"⏭️ Sắp tới: <@{upcoming['discord_id']}> — "
            f"`{next_date.strftime('%d/%m')}` ({when})",
            color=BIRTHDAY_COLOR,
        )
        for month, lines in by_month.items():
            embed.add_field(
                name=f"🗓️ {MONTH_NAMES[month - 1]}", value="\n".join(lines), inline=False
            )
        embed.set_footer(text=f"Tổng cộng {len(rows)} người")

        await interaction.response.send_message(
            embed=embed, allowed_mentions=discord.AllowedMentions.none()
        )

    async def _do_remove(
        self, interaction: discord.Interaction, user: Optional[discord.Member]
    ) -> None:
        if not await self._precheck(interaction):
            return

        target = user or interaction.user
        removed = await queries.delete_birthday(self.db, interaction.guild_id, target.id)
        msg = (
            f"🗑️ Đã xoá sinh nhật của {target.mention}."
            if removed
            else f"❌ {target.mention} chưa có trong danh sách."
        )
        await interaction.response.send_message(
            msg, allowed_mentions=discord.AllowedMentions.none()
        )

    # ------------------------------------------------------------------ #
    #  Daily announcement                                                  #
    # ------------------------------------------------------------------ #

    async def announce_today(self, channel: discord.abc.Messageable) -> int:
        """Post today's birthday wishes to the channel. Returns people wished."""
        guild = getattr(channel, "guild", None)
        if guild is None:
            log.error("🎂 Birthday channel is not in a server")
            return 0
        if not self.db.ready:
            log.warning("🎂 Birthday DB not ready, skipping announcement")
            return 0

        today = _today()
        rows = await queries.birthdays_on(self.db, guild.id, _celebrated_today(today))
        if not rows:
            return 0

        # Mentions inside an embed never ping, so tag people in the content too.
        mentions = " ".join(f"<@{r['discord_id']}>" for r in rows)
        await channel.send(
            content=f"🎉 {mentions}",
            embed=build_birthday_embed(rows, today),
            allowed_mentions=discord.AllowedMentions(users=True),
        )
        return len(rows)
