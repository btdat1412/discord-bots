import logging
import os

from src.shared.database import Database

from .gym_rat_bot import GymRatBot
from src.shared.storage import ImageStorage

log = logging.getLogger(__name__)


def setup(bot):
    db = Database()
    storage = ImageStorage()
    GymRatBot(bot, db, storage)

    @bot.event_listener("on_ready")
    async def _init_gym_db():
        dsn = os.getenv("GYM_RAT_DATABASE_URL", "")
        if not dsn:
            log.error("GYM_RAT_DATABASE_URL is not set — gym-rat DB disabled")
            return
        try:
            await db.connect(dsn)
            log.info("Gym Rat database connected")
        except Exception:
            log.exception("Failed to connect Gym Rat database")

        storage.connect()
