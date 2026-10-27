"""Birthday query functions — operate on the bot's Database instance."""

from src.shared.database import Database


async def upsert_birthday(
    db: Database,
    guild_id: int,
    discord_id: int,
    day: int,
    month: int,
    added_by: int,
) -> bool:
    """Insert or replace a birthday. Returns True if new, False if updated."""
    return await db.fetchval(
        """
        INSERT INTO birthdays (guild_id, discord_id, day, month, added_by)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (guild_id, discord_id)
        DO UPDATE SET day = $3, month = $4, added_by = $5, updated_at = NOW()
        RETURNING (xmax = 0)
        """,
        guild_id,
        discord_id,
        day,
        month,
        added_by,
    )


async def delete_birthday(db: Database, guild_id: int, discord_id: int) -> bool:
    result = await db.execute(
        "DELETE FROM birthdays WHERE guild_id = $1 AND discord_id = $2",
        guild_id,
        discord_id,
    )
    return result != "DELETE 0"


async def list_birthdays(db: Database, guild_id: int):
    return await db.fetch(
        """
        SELECT discord_id, day, month FROM birthdays
        WHERE guild_id = $1
        ORDER BY month, day
        """,
        guild_id,
    )


async def birthdays_on(db: Database, guild_id: int, dates: list[tuple[int, int]]):
    """Birthdays falling on any of the given (day, month) pairs."""
    days = [d for d, _ in dates]
    months = [m for _, m in dates]
    return await db.fetch(
        """
        SELECT discord_id, day, month FROM birthdays
        WHERE guild_id = $1
          AND (day, month) IN (
              SELECT * FROM UNNEST($2::smallint[], $3::smallint[])
          )
        ORDER BY discord_id
        """,
        guild_id,
        days,
        months,
    )
