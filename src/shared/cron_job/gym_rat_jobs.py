import logging

from discord.ext import commands

from src.shared.job_manager import JobConfig, vietnam_time

log = logging.getLogger(__name__)


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
        await channel.send("Hôm nay mấy con ghệ nhớ điểm danh đấy nhé 💪\nDùng `/checkin` hoặc `!gymrat checkin` để điểm danh!")
        log.info("📅 Daily gym reminder sent successfully")

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
