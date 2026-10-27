"""
Pre-defined cron job functions for the Birthday bot.
"""

import logging

from discord.ext import commands

from src.shared.job_manager import JobConfig, vietnam_time

log = logging.getLogger(__name__)


async def daily_birthday_job(bot: commands.Bot, channel_id: int, **kwargs):
    birthday = getattr(bot, "birthday_bot", None)
    if birthday is None:
        log.error("📅 BirthdayBot not found on the bot instance")
        return

    channel = bot.get_channel(channel_id)
    if not channel:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            log.error("📅 Cannot find channel with ID %s", channel_id)
            return

    wished = await birthday.announce_today(channel)
    if wished:
        log.info("📅 Wished happy birthday to %d people", wished)
    else:
        log.info("📅 No birthday today")


def create_daily_birthday_job(channel_id: int, hour: int = 7, minute: int = 0) -> JobConfig:
    """Post birthday wishes every morning, 07:00 Vietnam time by default."""
    return JobConfig(
        name="daily_birthday",
        description=f"Birthday wishes at {hour:02d}:{minute:02d} Vietnam time",
        schedule_time=vietnam_time(hour, minute),
        job_function=daily_birthday_job,
        kwargs={"channel_id": channel_id},
    )
