# bot_runner.py
import asyncio
import importlib
import logging
import discord

from src.shared.config import BotCfg
from src.shared.logging_conf import setup_logging
from base_bot import BaseBot

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
    setup_logging()
    intents = make_intents(cfg.intents)
    bot = BaseBot(prefix="!", intents=intents)

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

    await bot.start(cfg.token)


def run_bot(cfg: BotCfg):
    try:
        asyncio.run(run_bot_async(cfg))
    except KeyboardInterrupt:
        pass
    except Exception:
        log.exception("Bot '%s' crashed", cfg.name)
