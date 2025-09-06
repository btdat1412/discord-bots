# bot_runner.py
import asyncio
import importlib
import logging
import discord

from src.shared.config import BotCfg
from src.shared.logging_conf import setup_logging
from src.core.base_bot import BaseBot
from src.shared.job_manager import CronJobManager

log = logging.getLogger(__name__)


def make_intents(cfg) -> discord.Intents:
    intents = discord.Intents.none()
    intents.guilds = cfg.guilds
    intents.members = cfg.members
    intents.messages = cfg.messages
    intents.message_content = cfg.message_content
    intents.reactions = cfg.reactions
    return intents


async def run_bot_async(cfg: BotCfg):
    """
    Run bot with auto-discovered cron jobs.

    Args:
        cfg: Bot configuration
    """
    setup_logging()
    intents = make_intents(cfg.intents)
    bot = BaseBot(prefix="!", intents=intents)

    # Attach config to bot instance so modules can access it
    bot.config = cfg

    # Initialize job manager
    job_manager = CronJobManager(bot)
    bot.job_manager = job_manager

    # Load bot modules/cogs
    for mod_path in cfg.cogs:
        try:
            mod = importlib.import_module(mod_path)
            if hasattr(mod, "setup"):
                mod.setup(bot)
                log.info("Loaded module: %s", mod_path)
            else:
                log.warning("Module %s has no setup(bot)", mod_path)
        except Exception:
            log.exception("Failed to load %s", mod_path)

    # Auto-discover and setup cron jobs
    await job_manager.auto_setup_jobs(cfg.name)

    try:
        await bot.start(cfg.token)
    finally:
        # Clean shutdown - stop all jobs
        if hasattr(bot, "job_manager"):
            bot.job_manager.stop_all_jobs()


def run_bot(cfg: BotCfg):
    """
    Run bot with auto-discovered cron jobs.

    Args:
        cfg: Bot configuration
    """
    try:
        asyncio.run(run_bot_async(cfg))
    except KeyboardInterrupt:
        log.info("Bot '%s' stopped by user", cfg.name)
    except Exception:
        log.exception("Bot '%s' crashed", cfg.name)
