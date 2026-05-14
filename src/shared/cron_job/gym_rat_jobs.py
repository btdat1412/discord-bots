import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from src.shared.job_manager import JobConfig, vietnam_time

log = logging.getLogger(__name__)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


async def daily_gym_reminder(bot: commands.Bot, channel_id: int, **kwargs):
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception:
                log.error("📅 Cannot find channel with ID %s", channel_id)
                return

        log.info("📅 Sending daily gym reminder to channel %s", channel.name)
        await channel.send(
            "Hôm nay mấy con ghệ nhớ điểm danh đấy nhé 💪\n"
            "Dùng `/checkin` hoặc `!gymrat checkin` để điểm danh!"
        )

        # Legit check — find slackers who skipped 3+ days
        gym_rat = getattr(bot, "gym_rat_bot", None)
        if not gym_rat or not gym_rat.db.ready:
            log.warning("📅 Gym Rat DB not ready, skipping legit check")
            return

        from src.bots.gym_rat_bot import queries

        today = datetime.now(VN_TZ).date()
        guild = getattr(channel, "guild", None)

        slackers = await queries.get_slackers(gym_rat.db, today, min_skip_days=3)
        log.info("📅 Found %d slacker candidate(s) in DB", len(slackers))

        lines = []
        for slacker in slackers:
            discord_id = slacker["discord_id"]
            last_checkin = slacker["last_checkin"]
            days_missed = (today - last_checkin).days

            # Resolve the user just to get a fresh display name + username (no ping)
            display_name = slacker["discord_name"]
            username = None
            user = None
            if guild is not None:
                user = guild.get_member(discord_id)
            if user is None:
                try:
                    user = await bot.fetch_user(discord_id)
                except Exception:
                    user = None
            if user is not None:
                display_name = getattr(user, "display_name", display_name)
                username = getattr(user, "name", None)

            tag = f" (@{username})" if username else ""
            lines.append(
                f"• **{display_name}**{tag} — **{days_missed} ngày** không điểm danh "
                f"(lần cuối: {last_checkin.strftime('%d/%m/%Y')})"
            )

        if not lines:
            log.info("📅 No slackers found, everyone is legit 💪")
            return

        embed = discord.Embed(
            title="⚠️ Gym Legit Check",
            description="Heads up — mấy con ghệ này đang trốn tập 👀\n\n"
            + "\n".join(lines),
            color=discord.Color.red(),
        )
        await channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        log.info("📅 Legit check done, found %d slacker(s)", len(lines))

    except Exception as e:
        log.exception("📅 Error in daily gym reminder: %s", e)


def create_daily_reminder_job(channel_id: int) -> JobConfig:
    return JobConfig(
        name="daily_gym_reminder",
        description="Daily gym reminder at 7:00 AM Vietnam time",
        schedule_time=vietnam_time(7, 0),
        job_function=daily_gym_reminder,
        kwargs={"channel_id": channel_id},
    )
