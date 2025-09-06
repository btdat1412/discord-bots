"""
Pre-defined cron job functions for TiGiaBot.
These jobs can be injected into any bot instance.
"""

import logging
from typing import Optional
from discord.ext import commands

from src.shared.job_manager import JobConfig, vietnam_time

log = logging.getLogger(__name__)


async def daily_ti_gia_job(bot: commands.Bot, channel_id: int, **kwargs):
    """
    Daily ti-gia job function.

    Args:
        bot: The Discord bot instance
        channel_id: Discord channel ID to send the message to
        **kwargs: Additional job parameters (title, footer)
    """
    try:
        # Find TiGiaBot instance - simple duck typing
        ti_gia_bot = None
        for attr_name in dir(bot):
            attr = getattr(bot, attr_name, None)
            if hasattr(attr, "execute_ti_gia"):
                ti_gia_bot = attr
                break

        if not ti_gia_bot:
            log.error("📅 TiGiaBot not found in bot instance")
            return

        # Get the channel
        channel = bot.get_channel(channel_id)
        if not channel:
            log.error("📅 Cannot find channel with ID %s", channel_id)
            return

        log.info("📅 Sending daily ti-gia update to channel %s", channel.name)

        # Execute ti-gia with custom title/footer if provided
        title = kwargs.get("title", "🌅 Tỉ giá & Giá vàng hôm nay")
        footer = kwargs.get("footer", "Cập nhật lúc 9:00 sáng hàng ngày")

        embed = await ti_gia_bot.execute_ti_gia(title=title, footer=footer)

        # Send the message
        await channel.send(embed=embed)
        log.info("📅 Daily ti-gia update sent successfully")

    except Exception as e:
        log.exception("📅 Error in daily ti-gia job: %s", e)


# Daily morning ti-gia job at 9:00 AM Vietnam time
def create_daily_morning_job(channel_id: int) -> JobConfig:
    """Create a daily morning ti-gia job at 9:00 AM Vietnam time."""
    return JobConfig(
        name="daily_ti_gia",
        description="Daily ti-gia update at 9:00 AM Vietnam time",
        schedule_time=vietnam_time(9, 0),
        job_function=daily_ti_gia_job,
        kwargs={"channel_id": channel_id},
    )
