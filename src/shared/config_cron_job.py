"""
Cron job configuration mappings.
Defines which bots have which cron jobs available.
"""

import os
import logging
from typing import List, Callable, Optional

from src.shared.job_manager import JobConfig

log = logging.getLogger(__name__)


def get_ti_gia_jobs() -> List[JobConfig]:
    jobs = []

    channel_id_str = os.getenv("TI_GIA_DAILY_CHANNEL_ID", "").strip()
    if channel_id_str:
        try:
            from src.shared.cron_job.ti_gia_jobs import create_daily_morning_job

            channel_id = int(channel_id_str)
            jobs.append(create_daily_morning_job(channel_id))
            log.info("🔧 Configured daily ti-gia job for channel: %s", channel_id)
        except ValueError:
            log.error("🔧 Invalid TI_GIA_DAILY_CHANNEL_ID: %s", channel_id_str)

    return jobs


def get_gym_rat_jobs() -> List[JobConfig]:
    jobs = []

    channel_id_str = os.getenv("GYM_RAT_DAILY_CHANNEL_ID", "").strip()
    if channel_id_str:
        try:
            from src.shared.cron_job.gym_rat_jobs import create_daily_reminder_job

            channel_id = int(channel_id_str)
            jobs.append(create_daily_reminder_job(channel_id))
            log.info("🔧 Configured daily gym reminder for channel: %s", channel_id)
        except ValueError:
            log.error("🔧 Invalid GYM_RAT_DAILY_CHANNEL_ID: %s", channel_id_str)

    return jobs


def get_secret_santa_jobs() -> List[JobConfig]:
    """Needs no channel id — each open game records its own channel."""
    from src.shared.cron_job.secret_santa_jobs import create_daily_bump_job

    hour_str = os.getenv("SECRET_SANTA_BUMP_HOUR", "8").strip()
    try:
        hour = int(hour_str)
    except ValueError:
        log.error("🔧 Invalid SECRET_SANTA_BUMP_HOUR: %s — using 8", hour_str)
        hour = 8

    log.info("🔧 Configured daily Secret Santa lobby bump at %02d:00", hour)
    return [create_daily_bump_job(hour)]


def get_birthday_jobs() -> List[JobConfig]:
    jobs = []

    channel_id_str = os.getenv("BIRTHDAY_CHANNEL_ID", "").strip()
    if not channel_id_str:
        log.warning("🔧 BIRTHDAY_CHANNEL_ID is not set — no birthday wishes")
        return jobs

    hour_str = os.getenv("BIRTHDAY_HOUR", "7").strip()
    try:
        hour = int(hour_str)
    except ValueError:
        log.error("🔧 Invalid BIRTHDAY_HOUR: %s — using 7", hour_str)
        hour = 7

    try:
        from src.shared.cron_job.birthday_jobs import create_daily_birthday_job

        channel_id = int(channel_id_str)
        jobs.append(create_daily_birthday_job(channel_id, hour))
        log.info(
            "🔧 Configured daily birthday wishes at %02d:00 for channel: %s",
            hour,
            channel_id,
        )
    except ValueError:
        log.error("🔧 Invalid BIRTHDAY_CHANNEL_ID: %s", channel_id_str)

    return jobs


# Bot name to job configuration function mapping
BOT_CRON_MAPPINGS = {
    "ti-gia": get_ti_gia_jobs,
    "gym-rat": get_gym_rat_jobs,
    "secret-santa": get_secret_santa_jobs,
    "birthday": get_birthday_jobs,
}


# Function to get all cron jobs for bot
def get_jobs_for_bot(bot_name: str) -> List[JobConfig]:
    if bot_name not in BOT_CRON_MAPPINGS:
        log.debug("🔧 No cron job configuration found for bot: %s", bot_name)
        return []

    try:
        job_getter = BOT_CRON_MAPPINGS[bot_name]
        jobs = job_getter()
        return jobs
    except Exception as e:
        log.exception("🔧 Error getting cron jobs for bot %s: %s", bot_name, e)
        return []
