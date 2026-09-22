"""Persistence for Secret Santa — operates on the shared Database instance.

``answers`` is stored as JSONB. asyncpg has no JSON codec registered on the
shared pool, so it is encoded with ``json.dumps`` on write (with an explicit
``::jsonb`` cast) and decoded on read by :func:`participant_answers`.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

from src.shared.database import Database

log = logging.getLogger(__name__)

STATE_OPEN = "OPEN"
STATE_COMPLETED = "COMPLETED"
STATE_CANCELLED = "CANCELLED"

PROXY_PREFIX = "proxy:"
"""Synthetic user_id prefix for someone who is not in the Discord server.
Real participants always carry a Discord snowflake, so the prefix is enough to
tell the two apart anywhere in the code."""


def new_proxy_id() -> str:
    return f"{PROXY_PREFIX}{uuid.uuid4().hex[:12]}"


def is_proxy(user_id: str) -> bool:
    return user_id.startswith(PROXY_PREFIX)


# ---------------------------------------------------------------- games ----


async def create_game(
    db: Database,
    edition_key: str,
    guild_id: str,
    channel_id: str,
    message_id: str,
    host_id: str,
) -> asyncpg.Record:
    return await db.fetchrow(
        """
        INSERT INTO santa_games
            (edition_key, guild_id, channel_id, message_id, host_id, state)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
        """,
        edition_key,
        guild_id,
        channel_id,
        message_id,
        host_id,
        STATE_OPEN,
    )


async def get_game(db: Database, game_id: int) -> Optional[asyncpg.Record]:
    return await db.fetchrow("SELECT * FROM santa_games WHERE id = $1", game_id)


async def get_open_games(db: Database) -> List[asyncpg.Record]:
    """Every lobby still accepting joins."""
    return await db.fetch(
        "SELECT * FROM santa_games WHERE state = $1 ORDER BY id", STATE_OPEN
    )


async def get_open_game_in_guild(
    db: Database, guild_id: str
) -> Optional[asyncpg.Record]:
    """The newest lobby still open in this server, if there is one."""
    return await db.fetchrow(
        """
        SELECT * FROM santa_games
        WHERE guild_id = $1 AND state = $2
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        guild_id,
        STATE_OPEN,
    )


async def get_guild_games(
    db: Database, guild_id: str, limit: int = 25
) -> List[asyncpg.Record]:
    return await db.fetch(
        """
        SELECT g.*, COUNT(p.id) AS participant_count
        FROM santa_games g
        LEFT JOIN santa_participants p ON p.game_id = g.id
        WHERE g.guild_id = $1
        GROUP BY g.id
        ORDER BY g.created_at DESC
        LIMIT $2
        """,
        guild_id,
        limit,
    )


# ------------------------------------------------------- lobby messages ----


async def add_lobby_message(
    db: Database,
    game_id: int,
    channel_id: str,
    message_id: str,
    is_primary: bool = False,
) -> None:
    """Remember one more message that shows this game's buttons."""
    await db.execute(
        """
        INSERT INTO santa_lobby_messages
            (game_id, channel_id, message_id, is_primary)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT DO NOTHING
        """,
        game_id,
        channel_id,
        message_id,
        is_primary,
    )


async def get_lobby_messages(db: Database, game_id: int) -> List[asyncpg.Record]:
    return await db.fetch(
        """
        SELECT * FROM santa_lobby_messages
        WHERE game_id = $1
        ORDER BY is_primary DESC, id ASC
        """,
        game_id,
    )


async def get_open_lobby_messages(db: Database) -> List[asyncpg.Record]:
    """Every message of every open game — used to re-arm buttons on startup."""
    return await db.fetch(
        """
        SELECT m.*, g.edition_key
        FROM santa_lobby_messages m
        JOIN santa_games g ON g.id = m.game_id
        WHERE g.state = $1
        ORDER BY m.game_id, m.id
        """,
        STATE_OPEN,
    )


async def forget_lobby_message(db: Database, game_id: int, message_id: str) -> None:
    """Drop a message that no longer exists in Discord."""
    await db.execute(
        """
        DELETE FROM santa_lobby_messages
        WHERE game_id = $1 AND message_id = $2
        """,
        game_id,
        message_id,
    )


async def get_bump_messages(db: Database, game_id: int) -> List[asyncpg.Record]:
    """The pushed-down copies, i.e. everything except the original."""
    return await db.fetch(
        """
        SELECT * FROM santa_lobby_messages
        WHERE game_id = $1 AND is_primary = FALSE
        ORDER BY id
        """,
        game_id,
    )


# --------------------------------------------------------- participants ----


async def upsert_participant(
    db: Database,
    game_id: int,
    user_id: str,
    display_name: str,
    display_name_server: str,
    avatar_url: str,
    answers: Dict[str, str],
    registered_by: Optional[str] = None,
) -> asyncpg.Record:
    """Add a participant, or overwrite their answers if they re-join.

    ``registered_by`` is the Discord id of the member who entered this person
    on their behalf, and is ``None`` for everyone who joined themselves.
    """
    return await db.fetchrow(
        """
        INSERT INTO santa_participants
            (game_id, user_id, display_name, display_name_server,
             avatar_url, answers, registered_by)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
        ON CONFLICT (game_id, user_id) DO UPDATE SET
            display_name        = EXCLUDED.display_name,
            display_name_server = EXCLUDED.display_name_server,
            avatar_url          = EXCLUDED.avatar_url,
            answers             = EXCLUDED.answers,
            registered_by       = EXCLUDED.registered_by,
            updated_at          = NOW()
        RETURNING *
        """,
        game_id,
        user_id,
        display_name,
        display_name_server,
        avatar_url,
        json.dumps(answers),
        registered_by,
    )


async def get_proxies_by(
    db: Database, game_id: int, registrar_id: str
) -> List[asyncpg.Record]:
    """Everyone ``registrar_id`` entered on someone else's behalf."""
    return await db.fetch(
        """
        SELECT * FROM santa_participants
        WHERE game_id = $1 AND registered_by = $2
        ORDER BY joined_at ASC
        """,
        game_id,
        registrar_id,
    )


async def get_participant(
    db: Database, game_id: int, user_id: str
) -> Optional[asyncpg.Record]:
    return await db.fetchrow(
        "SELECT * FROM santa_participants WHERE game_id = $1 AND user_id = $2",
        game_id,
        user_id,
    )


async def remove_participant(db: Database, game_id: int, user_id: str) -> bool:
    result = await db.execute(
        "DELETE FROM santa_participants WHERE game_id = $1 AND user_id = $2",
        game_id,
        user_id,
    )
    return result != "DELETE 0"


async def remove_participant_with_proxies(
    db: Database, game_id: int, user_id: str
) -> List[str]:
    """Remove a member and everyone they registered dùm, atomically.

    The people they entered have no Discord account of their own — their
    assignment is delivered to whoever registered them. Leaving them behind
    would strand them in the game and keep DMing someone who has left, so they
    go too. Rejoining means registering them again.

    Returns the display names of the proxies that were removed.
    """
    async with db.transaction() as conn:
        proxies = await conn.fetch(
            """
            SELECT display_name FROM santa_participants
            WHERE game_id = $1 AND registered_by = $2
            """,
            game_id,
            user_id,
        )
        await conn.execute(
            """
            DELETE FROM santa_participants
            WHERE game_id = $1 AND (user_id = $2 OR registered_by = $2)
            """,
            game_id,
            user_id,
        )
    return [r["display_name"] for r in proxies]


async def is_participant(db: Database, game_id: int, user_id: str) -> bool:
    return bool(
        await db.fetchval(
            """
            SELECT 1 FROM santa_participants
            WHERE game_id = $1 AND user_id = $2
            """,
            game_id,
            user_id,
        )
    )


async def get_participants(db: Database, game_id: int) -> List[asyncpg.Record]:
    return await db.fetch(
        """
        SELECT * FROM santa_participants
        WHERE game_id = $1
        ORDER BY joined_at ASC
        """,
        game_id,
    )


async def count_participants(db: Database, game_id: int) -> int:
    return await db.fetchval(
        "SELECT COUNT(*) FROM santa_participants WHERE game_id = $1", game_id
    )


async def set_public_opt_in(
    db: Database, game_id: int, user_id: str, public: bool
) -> None:
    await db.execute(
        """
        UPDATE santa_participants
        SET public_opt_in = $3, updated_at = NOW()
        WHERE game_id = $1 AND user_id = $2
        """,
        game_id,
        user_id,
        public,
    )


async def get_assignment_for(
    db: Database, game_id: int, user_id: str
) -> Optional[asyncpg.Record]:
    """The participant row of the person ``user_id`` was assigned to gift."""
    return await db.fetchrow(
        """
        SELECT target.*
        FROM santa_participants giver
        JOIN santa_participants target
          ON target.game_id = giver.game_id
         AND target.user_id = giver.assigned_to
        WHERE giver.game_id = $1 AND giver.user_id = $2
        """,
        game_id,
        user_id,
    )


async def latest_completed_game_for_user(
    db: Database, user_id: str, guild_id: Optional[str] = None
) -> Optional[asyncpg.Record]:
    """Latest finished game where the user played, or registered someone.

    ``guild_id`` narrows the search to one server. It is left out when the
    lookup comes from a DM, where there is no server to scope to.
    """
    return await db.fetchrow(
        """
        SELECT g.*
        FROM santa_games g
        JOIN santa_participants p ON p.game_id = g.id
        WHERE ($1::text IS NULL OR g.guild_id = $1)
          AND (p.user_id = $2 OR p.registered_by = $2)
          AND g.state = $3
          AND p.assigned_to IS NOT NULL
        ORDER BY g.completed_at DESC NULLS LAST, g.id DESC
        LIMIT 1
        """,
        guild_id,
        user_id,
        STATE_COMPLETED,
    )


def participant_answers(row: asyncpg.Record) -> Dict[str, Any]:
    """Decode the JSONB ``answers`` column of a participant row."""
    raw = row["answers"]
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Malformed answers JSON on participant row %s", row["id"])
            return {}
    return raw or {}


# ------------------------------------------------------- start / commit ----


async def commit_start(
    db: Database,
    game_id: int,
    assignments: Dict[str, str],
    deliveries: List[Tuple[str, str, str, str]],
) -> None:
    """Write every assignment, the delivery log and the new state, atomically.

    Either all rows land or none do — a partially matched game is never
    visible to another query. This runs only once every DM has already been
    delivered, so a game marked COMPLETED always has everyone notified.

    ``deliveries`` holds ``(user_id, recipient_id, channel_id, message_id)``
    per DM sent.
    """
    async with db.transaction() as conn:
        for giver_id, receiver_id in assignments.items():
            result = await conn.execute(
                """
                UPDATE santa_participants
                SET assigned_to = $3, updated_at = NOW()
                WHERE game_id = $1 AND user_id = $2
                """,
                game_id,
                giver_id,
                receiver_id,
            )
            if result == "UPDATE 0":
                raise RuntimeError(
                    f"participant {giver_id} vanished from game {game_id} "
                    f"while starting"
                )

        result = await conn.execute(
            """
            UPDATE santa_games
            SET state = $2, started_at = NOW(), completed_at = NOW()
            WHERE id = $1 AND state = $3
            """,
            game_id,
            STATE_COMPLETED,
            STATE_OPEN,
        )
        if result == "UPDATE 0":
            # Someone closed the game while the DMs were going out. Raising
            # rolls the whole transaction back, so the assignments written
            # above are discarded rather than left on a non-open game.
            raise RuntimeError(
                f"game {game_id} was no longer open when the draw committed"
            )

        for user_id, recipient_id, channel_id, message_id in deliveries:
            await conn.execute(
                """
                INSERT INTO santa_deliveries
                    (game_id, user_id, recipient_id, dm_channel_id,
                     dm_message_id)
                VALUES ($1, $2, $3, $4, $5)
                """,
                game_id,
                user_id,
                recipient_id,
                channel_id,
                message_id,
            )


# ------------------------------------------------------------ delivery ----


async def get_deliveries(db: Database, game_id: int) -> List[asyncpg.Record]:
    return await db.fetch(
        "SELECT * FROM santa_deliveries WHERE game_id = $1", game_id
    )
