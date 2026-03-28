"""Gym Rat query functions — operate on the shared Database instance."""

from datetime import date, timedelta

from src.shared.database import Database


async def get_or_create_user(db: Database, discord_id: int, discord_name: str):
    return await db.fetchrow(
        """
        INSERT INTO gym_users (discord_id, discord_name)
        VALUES ($1, $2)
        ON CONFLICT (discord_id)
        DO UPDATE SET discord_name = $2, updated_at = NOW()
        RETURNING *
        """,
        discord_id,
        discord_name,
    )


async def checkin(
    db: Database, user_id: int, checkin_date: date, image_url: str | None = None
) -> bool:
    """Insert a check-in. Returns True if new, False if already existed.
    If image_url is provided and check-in already exists, updates the image."""
    row = await db.fetchrow(
        """
        INSERT INTO gym_checkins (user_id, checkin_date, image_url)
        VALUES ($1, $2, $3)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        user_id,
        checkin_date,
        image_url,
    )
    is_new = row is not None

    # If already checked in but user is adding/updating an image
    if not is_new and image_url:
        await db.execute(
            """
            UPDATE gym_checkins SET image_url = $3
            WHERE user_id = $1 AND checkin_date = $2
            """,
            user_id,
            checkin_date,
            image_url,
        )

    return is_new


async def get_checkins_range(
    db: Database, user_id: int, start_date: date, end_date: date
) -> list[date]:
    rows = await db.fetch(
        """
        SELECT checkin_date FROM gym_checkins
        WHERE user_id = $1 AND checkin_date BETWEEN $2 AND $3
        ORDER BY checkin_date
        """,
        user_id,
        start_date,
        end_date,
    )
    return [r["checkin_date"] for r in rows]


async def get_total_checkins(db: Database, user_id: int) -> int:
    return await db.fetchval(
        "SELECT COUNT(*) FROM gym_checkins WHERE user_id = $1", user_id
    )


async def get_month_checkins(
    db: Database, user_id: int, year: int, month: int
) -> int:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return await db.fetchval(
        """
        SELECT COUNT(*) FROM gym_checkins
        WHERE user_id = $1 AND checkin_date >= $2 AND checkin_date < $3
        """,
        user_id,
        start,
        end,
    )


async def get_streak(db: Database, user_id: int, today: date) -> tuple[int, int]:
    """Returns (current_streak, longest_streak)."""
    rows = await db.fetch(
        """
        SELECT checkin_date FROM gym_checkins
        WHERE user_id = $1
        ORDER BY checkin_date DESC
        """,
        user_id,
    )

    if not rows:
        return 0, 0

    dates = [r["checkin_date"] for r in rows]

    # Current streak (must include today or yesterday)
    current = 0
    expected = today
    for d in dates:
        if d == expected:
            current += 1
            expected -= timedelta(days=1)
        elif d == today - timedelta(days=1) and current == 0:
            expected = d
            current = 1
            expected -= timedelta(days=1)
        else:
            break

    # Longest streak
    longest = 1
    streak = 1
    sorted_dates = sorted(dates)
    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] - sorted_dates[i - 1] == timedelta(days=1):
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 1

    return current, longest


async def get_leaderboard(db: Database, limit: int = 10):
    return await db.fetch(
        """
        SELECT u.discord_name, u.discord_id, COUNT(*) as total
        FROM gym_checkins c
        JOIN gym_users u ON u.id = c.user_id
        GROUP BY u.id, u.discord_name, u.discord_id
        ORDER BY total DESC
        LIMIT $1
        """,
        limit,
    )


async def get_monthly_leaderboard(
    db: Database, year: int, month: int, limit: int = 10
):
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return await db.fetch(
        """
        SELECT u.discord_name, u.discord_id, COUNT(*) as total
        FROM gym_checkins c
        JOIN gym_users u ON u.id = c.user_id
        WHERE c.checkin_date >= $1 AND c.checkin_date < $2
        GROUP BY u.id, u.discord_name, u.discord_id
        ORDER BY total DESC
        LIMIT $3
        """,
        start,
        end,
        limit,
    )


async def get_checkins_with_images(db: Database, user_id: int):
    """Get all check-ins that have images, newest first."""
    return await db.fetch(
        """
        SELECT checkin_date, image_url FROM gym_checkins
        WHERE user_id = $1 AND image_url IS NOT NULL
        ORDER BY checkin_date DESC
        """,
        user_id,
    )
