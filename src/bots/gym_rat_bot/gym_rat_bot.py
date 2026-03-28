import logging
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from src.shared.database import Database

from . import queries
from .contribution_graph import render_month_calendar
from src.shared.storage import ImageStorage

import io
import aiohttp

log = logging.getLogger(__name__)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
MEDALS = ["🥇", "🥈", "🥉"]


def _today() -> date:
    from datetime import datetime

    return datetime.now(VN_TZ).date()


class GymRatBot:

    def __init__(self, bot: commands.Bot, db: Database, storage: ImageStorage = None):
        self.bot = bot
        self.db = db
        self.storage = storage
        self._register_slash_commands()
        self._register_prefix_commands()

    # ------------------------------------------------------------------ #
    #  Slash commands                                                      #
    # ------------------------------------------------------------------ #

    def _register_slash_commands(self) -> None:
        # /checkin and /diemdanh — need optional image param, register directly
        @app_commands.command(name="checkin", description="Check in your gym day")
        @app_commands.describe(image="Upload a photo of your gym session")
        async def checkin(
            interaction: discord.Interaction, image: discord.Attachment = None
        ):
            await self._do_checkin(interaction, image)

        self.bot.tree.add_command(checkin)

        @app_commands.command(name="diemdanh", description="Điểm danh tập gym hôm nay")
        @app_commands.describe(image="Upload ảnh tập gym")
        async def diemdanh(
            interaction: discord.Interaction, image: discord.Attachment = None
        ):
            await self._do_checkin(interaction, image)

        self.bot.tree.add_command(diemdanh)

        # /gymhistory — needs optional user param, register directly
        @app_commands.command(
            name="gymhistory", description="View gym check-in history"
        )
        @app_commands.describe(user="User to view history for (default: yourself)")
        async def gymhistory(
            interaction: discord.Interaction, user: discord.Member = None
        ):
            await self._do_history(interaction, user)

        self.bot.tree.add_command(gymhistory)

        # /gymstats — needs optional user param
        @app_commands.command(
            name="gymstats", description="View gym check-in stats"
        )
        @app_commands.describe(user="User to view stats for (default: yourself)")
        async def gymstats(
            interaction: discord.Interaction, user: discord.Member = None
        ):
            await self._do_stats(interaction, user)

        self.bot.tree.add_command(gymstats)

        # /gymleaderboard — no params
        @self.bot.slash_command(
            name="gymleaderboard", description="View gym check-in leaderboard"
        )
        async def gymleaderboard(interaction: discord.Interaction):
            await self._do_leaderboard(interaction)

        # /gymgallery — optional user param
        @app_commands.command(
            name="gymgallery", description="Browse gym check-in photos"
        )
        @app_commands.describe(user="User to view photos for (default: yourself)")
        async def gymgallery(
            interaction: discord.Interaction, user: discord.Member = None
        ):
            await self._do_gallery(interaction, user)

        self.bot.tree.add_command(gymgallery)

    # ------------------------------------------------------------------ #
    #  Prefix commands (!gymrat checkin, !gymrat history, etc.)             #
    # ------------------------------------------------------------------ #

    def _register_prefix_commands(self) -> None:
        bot_ref = self

        @commands.group(name="gymrat", invoke_without_command=True)
        async def gymrat_group(ctx: commands.Context):
            await ctx.send_help(ctx.command)

        @gymrat_group.command(name="checkin")
        async def prefix_checkin(ctx: commands.Context):
            await bot_ref._do_checkin_prefix(ctx)

        @gymrat_group.command(name="diemdanh")
        async def prefix_diemdanh(ctx: commands.Context):
            await bot_ref._do_checkin_prefix(ctx)

        @gymrat_group.command(name="history")
        async def prefix_history(ctx: commands.Context, member: discord.Member = None):
            await bot_ref._do_history_prefix(ctx, member)

        @gymrat_group.command(name="stats")
        async def prefix_stats(ctx: commands.Context, member: discord.Member = None):
            await bot_ref._do_stats_prefix(ctx, member)

        @gymrat_group.command(name="leaderboard")
        async def prefix_leaderboard(ctx: commands.Context):
            await bot_ref._do_leaderboard_prefix(ctx)

        @gymrat_group.command(name="gallery")
        async def prefix_gallery(ctx: commands.Context, member: discord.Member = None):
            await bot_ref._do_gallery_prefix(ctx, member)

        self.bot.add_command(gymrat_group)

    # ------------------------------------------------------------------ #
    #  Core logic (shared by slash and prefix)                             #
    # ------------------------------------------------------------------ #

    async def _upload_attachment(
        self, attachment: discord.Attachment, discord_id: int
    ) -> str | None:
        """Download a Discord attachment and upload to S3."""
        if not self.storage or not self.storage.ready:
            return None
        try:
            file_bytes = await attachment.read()
            return await self.storage.upload(
                file_bytes, discord_id, attachment.content_type or "image/png"
            )
        except Exception:
            log.exception("Failed to process attachment")
            return None

    async def _do_checkin(
        self, interaction: discord.Interaction, attachment: discord.Attachment = None
    ) -> None:
        if not self.db.ready:
            await interaction.response.send_message(
                "Database is not connected yet. Please try again shortly.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)

        image_url = None
        if attachment:
            image_url = await self._upload_attachment(attachment, interaction.user.id)

        user = await queries.get_or_create_user(
            self.db, interaction.user.id, interaction.user.display_name
        )
        today = _today()
        is_new = await queries.checkin(self.db, user["id"], today, image_url)

        total = await queries.get_total_checkins(self.db, user["id"])
        current_streak, longest_streak = await queries.get_streak(
            self.db, user["id"], today
        )
        month_count = await queries.get_month_checkins(
            self.db, user["id"], today.year, today.month
        )

        if is_new:
            embed = discord.Embed(
                title="Gym Check-in",
                description=f"**{interaction.user.display_name}** checked in for today!",
                color=discord.Color.green(),
            )
        else:
            desc = "You already checked in today. Keep it up!"
            if image_url:
                desc = "Already checked in today — photo updated!"
            embed = discord.Embed(
                title="Already Checked In",
                description=desc,
                color=discord.Color.yellow(),
            )

        if image_url:
            embed.set_image(url=image_url)

        embed.add_field(name="Total Days", value=str(total), inline=True)
        embed.add_field(name="Current Streak", value=f"{current_streak} days", inline=True)
        embed.add_field(name="This Month", value=str(month_count), inline=True)
        embed.add_field(name="Longest Streak", value=f"{longest_streak} days", inline=True)
        embed.set_footer(text=f"{today.strftime('%A, %B %d, %Y')}")

        await interaction.followup.send(embed=embed)

    async def _do_checkin_prefix(self, ctx: commands.Context) -> None:
        if not self.db.ready:
            await ctx.send("Database is not connected yet. Please try again shortly.")
            return

        # Check for image attachments in the message
        image_url = None
        if ctx.message.attachments:
            image_url = await self._upload_attachment(ctx.message.attachments[0], ctx.author.id)

        user = await queries.get_or_create_user(
            self.db, ctx.author.id, ctx.author.display_name
        )
        today = _today()
        is_new = await queries.checkin(self.db, user["id"], today, image_url)

        total = await queries.get_total_checkins(self.db, user["id"])
        current_streak, longest_streak = await queries.get_streak(
            self.db, user["id"], today
        )
        month_count = await queries.get_month_checkins(
            self.db, user["id"], today.year, today.month
        )

        if is_new:
            embed = discord.Embed(
                title="Gym Check-in",
                description=f"**{ctx.author.display_name}** checked in for today!",
                color=discord.Color.green(),
            )
        else:
            desc = "You already checked in today. Keep it up!"
            if image_url:
                desc = "Already checked in today — photo updated!"
            embed = discord.Embed(
                title="Already Checked In",
                description=desc,
                color=discord.Color.yellow(),
            )

        if image_url:
            embed.set_image(url=image_url)

        embed.add_field(name="Total Days", value=str(total), inline=True)
        embed.add_field(name="Current Streak", value=f"{current_streak} days", inline=True)
        embed.add_field(name="This Month", value=str(month_count), inline=True)
        embed.add_field(name="Longest Streak", value=f"{longest_streak} days", inline=True)
        embed.set_footer(text=f"{today.strftime('%A, %B %d, %Y')}")

        await ctx.send(embed=embed)

    async def _build_history(
        self, target: discord.User | discord.Member, year: int, month: int
    ) -> tuple[discord.Embed, discord.File]:
        user = await queries.get_or_create_user(
            self.db, target.id, target.display_name
        )
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)

        checkin_dates = await queries.get_checkins_range(
            self.db, user["id"], start, end
        )
        total = await queries.get_total_checkins(self.db, user["id"])
        today = _today()
        current_streak, _ = await queries.get_streak(self.db, user["id"], today)
        month_count = await queries.get_month_checkins(
            self.db, user["id"], year, month
        )

        img_buf = render_month_calendar(set(checkin_dates), year, month)
        file = discord.File(img_buf, filename="gym_history.png")

        embed = discord.Embed(
            title=f"{target.display_name}'s Gym History",
            color=discord.Color.blurple(),
        )
        embed.set_image(url="attachment://gym_history.png")
        embed.set_footer(
            text=f"This month: {month_count} days | Total: {total} days | Streak: {current_streak} days"
        )

        return embed, file

    async def _do_history(
        self, interaction: discord.Interaction, member: discord.Member = None
    ) -> None:
        if not self.db.ready:
            await interaction.response.send_message(
                "Database is not connected yet.", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)

        target = member or interaction.user
        today = _today()
        embed, file = await self._build_history(target, today.year, today.month)
        view = HistoryView(self, target, today.year, today.month)

        await interaction.followup.send(embed=embed, file=file, view=view)

    async def _do_history_prefix(
        self, ctx: commands.Context, member: discord.Member = None
    ) -> None:
        if not self.db.ready:
            await ctx.send("Database is not connected yet.")
            return

        target = member or ctx.author
        today = _today()
        embed, file = await self._build_history(target, today.year, today.month)
        view = HistoryView(self, target, today.year, today.month)

        await ctx.send(embed=embed, file=file, view=view)

    async def _do_stats(
        self, interaction: discord.Interaction, member: discord.Member = None
    ) -> None:
        if not self.db.ready:
            await interaction.response.send_message(
                "Database is not connected yet.", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)

        target = member or interaction.user
        user = await queries.get_or_create_user(
            self.db, target.id, target.display_name
        )
        today = _today()

        total = await queries.get_total_checkins(self.db, user["id"])
        current_streak, longest_streak = await queries.get_streak(
            self.db, user["id"], today
        )
        month_count = await queries.get_month_checkins(
            self.db, user["id"], today.year, today.month
        )

        embed = discord.Embed(
            title=f"{target.display_name}'s Gym Stats",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Total Days", value=str(total), inline=True)
        embed.add_field(name="Current Streak", value=f"{current_streak} days", inline=True)
        embed.add_field(name="Longest Streak", value=f"{longest_streak} days", inline=True)
        embed.add_field(name="This Month", value=str(month_count), inline=True)
        embed.add_field(
            name="Member Since",
            value=user["created_at"].strftime("%B %d, %Y"),
            inline=True,
        )
        embed.set_footer(text=f"{today.strftime('%A, %B %d, %Y')}")

        await interaction.followup.send(embed=embed)

    async def _do_stats_prefix(
        self, ctx: commands.Context, member: discord.Member = None
    ) -> None:
        if not self.db.ready:
            await ctx.send("Database is not connected yet.")
            return

        target = member or ctx.author
        user = await queries.get_or_create_user(
            self.db, target.id, target.display_name
        )
        today = _today()

        total = await queries.get_total_checkins(self.db, user["id"])
        current_streak, longest_streak = await queries.get_streak(
            self.db, user["id"], today
        )
        month_count = await queries.get_month_checkins(
            self.db, user["id"], today.year, today.month
        )

        embed = discord.Embed(
            title=f"{target.display_name}'s Gym Stats",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Total Days", value=str(total), inline=True)
        embed.add_field(name="Current Streak", value=f"{current_streak} days", inline=True)
        embed.add_field(name="Longest Streak", value=f"{longest_streak} days", inline=True)
        embed.add_field(name="This Month", value=str(month_count), inline=True)
        embed.add_field(
            name="Member Since",
            value=user["created_at"].strftime("%B %d, %Y"),
            inline=True,
        )
        embed.set_footer(text=f"{today.strftime('%A, %B %d, %Y')}")

        await ctx.send(embed=embed)

    async def _do_leaderboard(self, interaction: discord.Interaction) -> None:
        if not self.db.ready:
            await interaction.response.send_message(
                "Database is not connected yet.", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        embed = await self._build_leaderboard_embed()
        await interaction.followup.send(embed=embed)

    async def _do_leaderboard_prefix(self, ctx: commands.Context) -> None:
        if not self.db.ready:
            await ctx.send("Database is not connected yet.")
            return

        embed = await self._build_leaderboard_embed()
        await ctx.send(embed=embed)

    async def _resolve_name(self, discord_id: int, fallback: str) -> str:
        """Get current display name from Discord, fall back to DB name."""
        try:
            user = self.bot.get_user(discord_id) or await self.bot.fetch_user(discord_id)
            return user.display_name
        except Exception:
            return fallback

    async def _build_leaderboard_embed(self) -> discord.Embed:
        today = _today()
        all_time = await queries.get_leaderboard(self.db, limit=10)
        monthly = await queries.get_monthly_leaderboard(
            self.db, today.year, today.month, limit=10
        )

        embed = discord.Embed(
            title="Gym Rat Leaderboard",
            color=discord.Color.gold(),
        )

        # All-time
        if all_time:
            lines = []
            for i, row in enumerate(all_time):
                medal = MEDALS[i] if i < 3 else f"**{i + 1}.**"
                name = await self._resolve_name(row["discord_id"], row["discord_name"])
                lines.append(f"{medal} {name} — {row['total']} days")
            embed.add_field(
                name="All Time", value="\n".join(lines), inline=False
            )
        else:
            embed.add_field(
                name="All Time", value="No check-ins yet!", inline=False
            )

        # This month
        month_name = today.strftime("%B %Y")
        if monthly:
            lines = []
            for i, row in enumerate(monthly):
                medal = MEDALS[i] if i < 3 else f"**{i + 1}.**"
                name = await self._resolve_name(row["discord_id"], row["discord_name"])
                lines.append(f"{medal} {name} — {row['total']} days")
            embed.add_field(
                name=month_name, value="\n".join(lines), inline=False
            )
        else:
            embed.add_field(
                name=month_name, value="No check-ins this month!", inline=False
            )

        return embed

    # ------------------------------------------------------------------ #
    #  Gallery                                                             #
    # ------------------------------------------------------------------ #

    async def _do_gallery(
        self, interaction: discord.Interaction, member: discord.Member = None
    ) -> None:
        if not self.db.ready:
            await interaction.response.send_message(
                "Database is not connected yet.", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)

        target = member or interaction.user
        user = await queries.get_or_create_user(
            self.db, target.id, target.display_name
        )
        photos = await queries.get_checkins_with_images(self.db, user["id"])

        if not photos:
            await interaction.followup.send(
                embed=discord.Embed(
                    title=f"{target.display_name}'s Gym Gallery",
                    description="No photos yet! Use `/checkin` with an image to add one.",
                    color=discord.Color.blurple(),
                )
            )
            return

        embed = self._build_gallery_embed(target, photos, 0)
        view = GalleryView(self, target, photos, 0)
        await interaction.followup.send(embed=embed, view=view)

    async def _do_gallery_prefix(
        self, ctx: commands.Context, member: discord.Member = None
    ) -> None:
        if not self.db.ready:
            await ctx.send("Database is not connected yet.")
            return

        target = member or ctx.author
        user = await queries.get_or_create_user(
            self.db, target.id, target.display_name
        )
        photos = await queries.get_checkins_with_images(self.db, user["id"])

        if not photos:
            await ctx.send(
                embed=discord.Embed(
                    title=f"{target.display_name}'s Gym Gallery",
                    description="No photos yet! Use `!gymrat checkin` with an image to add one.",
                    color=discord.Color.blurple(),
                )
            )
            return

        embed = self._build_gallery_embed(target, photos, 0)
        view = GalleryView(self, target, photos, 0)
        await ctx.send(embed=embed, view=view)

    def _build_gallery_embed(
        self, target, photos: list, index: int
    ) -> discord.Embed:
        photo = photos[index]
        checkin_date = photo["checkin_date"]

        embed = discord.Embed(
            title=f"{target.display_name}'s Gym Gallery",
            description=f"**{checkin_date.strftime('%A, %B %d, %Y')}**",
            color=discord.Color.blurple(),
        )
        embed.set_image(url=photo["image_url"])
        embed.set_footer(text=f"Photo {index + 1} of {len(photos)}")

        return embed


class HistoryView(discord.ui.View):
    """< Prev / Next > buttons for navigating months."""

    def __init__(
        self,
        bot_instance: GymRatBot,
        target: discord.User | discord.Member,
        year: int,
        month: int,
    ):
        super().__init__(timeout=120)
        self.bot_instance = bot_instance
        self.target = target
        self.year = year
        self.month = month

    def _prev_month(self) -> tuple[int, int]:
        if self.month == 1:
            return self.year - 1, 12
        return self.year, self.month - 1

    def _next_month(self) -> tuple[int, int]:
        if self.month == 12:
            return self.year + 1, 1
        return self.year, self.month + 1

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.year, self.month = self._prev_month()
        embed, file = await self.bot_instance._build_history(
            self.target, self.year, self.month
        )
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

    @discord.ui.button(label=">", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        today = _today()
        next_y, next_m = self._next_month()
        if date(next_y, next_m, 1) > date(today.year, today.month, 1):
            await interaction.response.defer()
            return
        self.year, self.month = next_y, next_m
        embed, file = await self.bot_instance._build_history(
            self.target, self.year, self.month
        )
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)


class GalleryView(discord.ui.View):
    """< Prev / Next > buttons for browsing gym photos."""

    def __init__(
        self,
        bot_instance: GymRatBot,
        target: discord.User | discord.Member,
        photos: list,
        index: int,
    ):
        super().__init__(timeout=120)
        self.bot_instance = bot_instance
        self.target = target
        self.photos = photos
        self.index = index

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.index <= 0:
            await interaction.response.defer()
            return
        self.index -= 1
        embed = self.bot_instance._build_gallery_embed(
            self.target, self.photos, self.index
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label=">", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.index >= len(self.photos) - 1:
            await interaction.response.defer()
            return
        self.index += 1
        embed = self.bot_instance._build_gallery_embed(
            self.target, self.photos, self.index
        )
        await interaction.response.edit_message(embed=embed, view=self)
