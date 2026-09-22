import logging
import os
from pathlib import Path

from src.shared.database import Database

from . import views
from .bot import SecretSantaBot

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def setup(bot):
    db = Database(migrations_dir=MIGRATIONS_DIR)
    santa = SecretSantaBot(bot, db)
    bot.secret_santa_bot = santa

    # Pagination on the participants list is matched by custom_id, so those
    # buttons keep working after a restart instead of dying with Discord's
    # "didn't respond in time".
    bot.add_dynamic_items(views.PaginationButton)

    @bot.event_listener("on_message")
    async def _dm_lookup(message):
        # Any DM to the bot means "show me my assignment again". Slash commands
        # are guild-scoped and do not exist in DMs, so this is the private way
        # in. Guild messages are ignored entirely.
        if message.author.bot or message.guild is not None:
            return
        try:
            await santa.handle_dm_lookup(message)
        except Exception:
            log.exception("DM lookup failed for user %s", message.author.id)

    @bot.event_listener("on_ready")
    async def _init_santa_db():
        if db.ready:
            return

        # Each bot names its own DSN, so any one of them can be pointed at a
        # separate database later without touching the others.
        dsn = os.getenv("SECRET_SANTA_DATABASE_URL", "")
        if not dsn:
            log.error(
                "SECRET_SANTA_DATABASE_URL is not set — secret-santa DB disabled"
            )
            return

        try:
            await db.connect(dsn)
            log.info("Secret Santa database connected")
        except Exception:
            log.exception("Failed to connect Secret Santa database")
            return

        # Buttons on lobbies opened before this restart need re-arming.
        await bot.secret_santa_bot.restore_open_lobbies()
