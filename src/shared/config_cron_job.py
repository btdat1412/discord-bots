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

    # Daily morning job
    channel_id_str = os.getenv("TI_GIA_DAILY_CHANNEL_ID")
    if channel_id_str:
        try:
            from src.shared.cron_job.ti_gia_jobs import create_daily_morning_job

            channel_id = int(channel_id_str)
            jobs.append(create_daily_morning_job(channel_id))
            log.info("🔧 Configured daily ti-gia job for channel: %s", channel_id)
        except ValueError:
            log.error("🔧 Invalid TI_GIA_DAILY_CHANNEL_ID: %s", channel_id_str)

    return jobs


# Bot name to job configuration function mapping
BOT_CRON_MAPPINGS = {
    "ti-gia": get_ti_gia_jobs,
    # "crypto-bot": get_crypto_jobs,
    # "weather-bot": get_weather_jobs,
    # Add more bots here...
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
