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
        slackers = await queries.get_slackers(gym_rat.db, today, min_skip_days=3)

        if not slackers:
            log.info("📅 No slackers found, everyone is legit 💪")
            return

        for slacker in slackers:
            discord_id = slacker["discord_id"]
            last_checkin = slacker["last_checkin"]
            days_missed = (today - last_checkin).days

            # Try to get current display name
            try:
                member = bot.get_user(discord_id) or await bot.fetch_user(discord_id)
                name = member.display_name
            except Exception:
                name = slacker["discord_name"]

            embed = discord.Embed(
                title="⚠️ Gym Legit Check",
                description=(
                    f"**{name}** đã **{days_missed} ngày** không điểm danh!\n"
                    f"Lần cuối check-in: **{last_checkin.strftime('%d/%m/%Y')}**\n\n"
                    f"Kick con ghệ này hay không?\n"
                    f"👍 = Kick | 👎 = Tha"
                ),
                color=discord.Color.red(),
            )

            msg = await channel.send(embed=embed)
            await msg.add_reaction("👍")
            await msg.add_reaction("👎")

        log.info("📅 Legit check done, found %d slacker(s)", len(slackers))

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
