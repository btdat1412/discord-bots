"""
Pre-defined cron job functions for the Secret Santa bot.
"""

import logging

from discord.ext import commands

from src.shared.job_manager import JobConfig, vietnam_time

log = logging.getLogger(__name__)


async def daily_bump_job(bot: commands.Bot, **kwargs):
    """Push every open lobby back to the bottom of its channel.

    A lobby posted days ago scrolls out of sight in a chatty channel, and
    people give up rather than scroll for it. Once a morning the bot reposts
    it; the old pushed-down copy is deleted first, so the channel gains at
    most one lobby message per game.

    Needs no channel id: every open game already records its own channel.
    """
    santa = getattr(bot, "secret_santa_bot", None)
    if santa is None:
        log.error("📅 SecretSantaBot not found on the bot instance")
        return

    bumped = await santa.bump_all_open_games()
    if bumped:
        log.info("📅 Bumped %d open lobby/lobbies", bumped)
    else:
        log.info("📅 No open lobby to bump")


def create_daily_bump_job(hour: int = 8, minute: int = 0) -> JobConfig:
    """Repost open lobbies every morning, 08:00 Vietnam time by default."""
    return JobConfig(
        name="daily_santa_bump",
        description=(
            f"Repost open Secret Santa lobbies at "
            f"{hour:02d}:{minute:02d} Vietnam time"
        ),
        schedule_time=vietnam_time(hour, minute),
        job_function=daily_bump_job,
    )
