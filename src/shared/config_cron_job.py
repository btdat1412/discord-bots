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


# Bot name to job configuration function mapping
BOT_CRON_MAPPINGS = {
    "ti-gia": get_ti_gia_jobs,
    "gym-rat": get_gym_rat_jobs,
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
