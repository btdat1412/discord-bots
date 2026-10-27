import logging
import os
from pathlib import Path

from src.shared.database import Database

from .bot import BirthdayBot

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def setup(bot):
    db = Database(migrations_dir=MIGRATIONS_DIR)
    bot.birthday_bot = BirthdayBot(bot, db)

    @bot.event_listener("on_ready")
    async def _init_birthday_db():
        if db.ready:
            return

        dsn = os.getenv("BIRTHDAY_DATABASE_URL", "")
        if not dsn:
            log.error("BIRTHDAY_DATABASE_URL is not set — birthday DB disabled")
            return

        try:
            await db.connect(dsn)
            log.info("Birthday database connected")
        except Exception:
            log.exception("Failed to connect Birthday database")
