"""
Flexible cron job management system for Discord bots.
Allows injecting multiple scheduled tasks into any bot without hardcoding them.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import time
from dataclasses import dataclass

import pytz
from discord.ext import tasks, commands

log = logging.getLogger(__name__)


@dataclass
class JobConfig:
    """Configuration for a scheduled job."""

    name: str
    description: str
    schedule_time: time
    job_function: Callable
    enabled: bool = True
    kwargs: Optional[Dict[str, Any]] = None


class CronJobManager:
    """Manages multiple cron jobs for a Discord bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.jobs: Dict[str, tasks.Loop] = {}
        self.job_configs: Dict[str, JobConfig] = {}
        self._bot_ready = False

    async def auto_setup_jobs(self, bot_name: str) -> None:
        """
        Auto-discover and setup cron jobs for this bot based on configuration.

        Args:
            bot_name: Name of the bot (e.g., "ti-gia")
        """
        from src.shared.config_cron_job import get_jobs_for_bot

        # Get jobs from configuration
        discovered_jobs = get_jobs_for_bot(bot_name)

        # Add all discovered jobs
        if discovered_jobs:
            log.info(
                "🔧 Setting up %d configured job(s) for bot: %s",
                len(discovered_jobs),
                bot_name,
            )
            for job_config in discovered_jobs:
                try:
                    await self.add_job(job_config)
                except Exception as e:
                    log.exception(
                        "Failed to add configured job '%s': %s", job_config.name, e
                    )
        else:
            log.info("🔧 No cron jobs configured for bot: %s", bot_name)

    async def add_job(self, job_config: JobConfig) -> None:
        """Add a new scheduled job."""
        if not job_config.enabled:
            log.info("🔧 Job '%s' is disabled, skipping", job_config.name)
            return

        if job_config.name in self.jobs:
            log.warning("🔧 Job '%s' already exists, replacing", job_config.name)
            await self.remove_job(job_config.name)

        # Create the scheduled task
        @tasks.loop(time=job_config.schedule_time)
        async def job_task():
            try:
                log.info(
                    "🔧 Executing job '%s' - %s",
                    job_config.name,
                    job_config.description,
                )

                kwargs = job_config.kwargs or {}
                if asyncio.iscoroutinefunction(job_config.job_function):
                    await job_config.job_function(self.bot, **kwargs)
                else:
                    job_config.job_function(self.bot, **kwargs)

                log.info("🔧 Job '%s' completed successfully", job_config.name)
            except Exception as e:
                log.exception("🔧 Job '%s' failed: %s", job_config.name, e)

        @job_task.before_loop
        async def before_job():
            """Wait for bot to be ready before starting the job."""
            await self.bot.wait_until_ready()
            if not self._bot_ready:
                log.info("🔧 Bot is ready, jobs can now run")
                self._bot_ready = True

        self.jobs[job_config.name] = job_task
        self.job_configs[job_config.name] = job_config

        # Start the job
        job_task.start()
        log.info(
            "🔧 Added and started job '%s' at %s",
            job_config.name,
            job_config.schedule_time.strftime("%H:%M %Z"),
        )

    async def remove_job(self, job_name: str) -> bool:
        """Remove a scheduled job."""
        if job_name not in self.jobs:
            log.warning("🔧 Job '%s' not found", job_name)
            return False

        job_task = self.jobs[job_name]
        if job_task.is_running():
            job_task.cancel()

        del self.jobs[job_name]
        del self.job_configs[job_name]

        log.info("🔧 Removed job '%s'", job_name)
        return True

    def list_jobs(self) -> List[str]:
        """List all registered jobs."""
        return list(self.jobs.keys())

    def get_job_status(self, job_name: str) -> Optional[Dict[str, Any]]:
        """Get status information for a job."""
        if job_name not in self.jobs:
            return None

        job_task = self.jobs[job_name]
        job_config = self.job_configs[job_name]

        return {
            "name": job_name,
            "description": job_config.description,
            "schedule_time": job_config.schedule_time,
            "enabled": job_config.enabled,
            "running": job_task.is_running(),
            "next_iteration": job_task.next_iteration,
        }

    def stop_all_jobs(self):
        """Stop all running jobs."""
        for job_name, job_task in self.jobs.items():
            if job_task.is_running():
                job_task.cancel()
                log.info("🔧 Stopped job '%s'", job_name)

        log.info("🔧 All jobs stopped")


# Utility functions for creating common job schedules
def daily_at(hour: int, minute: int = 0, timezone: str = "Asia/Ho_Chi_Minh") -> time:
    """Create a daily schedule time."""
    tz = pytz.timezone(timezone)
    return time(hour=hour, minute=minute, tzinfo=tz)


def vietnam_time(hour: int, minute: int = 0) -> time:
    """Create a time in Vietnam timezone (Asia/Ho_Chi_Minh)."""
    return daily_at(hour, minute, "Asia/Ho_Chi_Minh")
