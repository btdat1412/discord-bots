"""Starting the exchange — all-or-nothing.

Discord has no transactions, so the closest honest equivalent is built here:

1. **Preflight** — really send a short DM to every participant. Opening a DM
   channel succeeds even for people who block DMs, so only an actual send
   proves the bot can reach them. If anyone is unreachable the run stops here:
   nothing is matched, nothing is saved, and the probes already sent are
   deleted again.
2. **Commit** — write every assignment and the new game state in one database
   transaction.
3. **Deliver** — send the assignment DMs, logging each one.
4. **Compensate** — if any delivery still fails, delete every assignment DM
   already sent and roll the database back to an open lobby.

The result is the property the old bot promised but did not have: either
everybody gets their assignment, or nobody does.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import asyncpg
import discord

from src.shared.database import Database

from . import queries, ui
from .matching import MatchError, build_assignments, santa_of
from .models import Edition

log = logging.getLogger(__name__)

# Discord's DM rate limits are per-recipient, but a burst of channel creations
# is still worth pacing on larger servers.
SEND_DELAY_SECONDS = 0.25


@dataclass
class ExchangeResult:
    ok: bool
    delivered: int = 0
    unreachable: List[str] = field(default_factory=list)
    """User ids the bot could not DM at all."""
    failed: List[str] = field(default_factory=list)
    """User ids whose assignment DM failed after the draw was committed."""
    rolled_back: bool = False
    error: Optional[str] = None

    def problem_report(self, edition: Edition) -> str:
        """Channel message explaining why nobody received anything."""
        copy = edition.copy
        if self.error:
            return copy.generic_failure.format(reason=self.error)

        if self.unreachable:
            mentions = "\n".join(f"• <@{uid}>" for uid in self.unreachable)
            return (
                f"{copy.unreachable_title}\n{mentions}\n\n{copy.unreachable_help}"
            )

        if self.failed:
            mentions = "\n".join(f"• <@{uid}>" for uid in self.failed)
            rolled = (
                copy.rolled_back_note
                if self.rolled_back
                else copy.rollback_broken_note
            )
            return (
                f"{copy.delivery_failed_title}\n{mentions}\n\n{rolled}"
            )

        return copy.generic_failure.format(
            reason="Unknown error — check the logs."
        )


async def _send_dm(
    user: discord.abc.User, **kwargs
) -> Optional[discord.Message]:
    """Send a DM, returning ``None`` when the user cannot be reached."""
    try:
        channel = user.dm_channel or await user.create_dm()
        return await channel.send(**kwargs)
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning("DM to %s failed: %s", user.id, exc)
        return None


async def _delete_quietly(message: discord.Message) -> bool:
    try:
        await message.delete()
        return True
    except discord.HTTPException as exc:
        log.warning("Could not delete DM %s: %s", message.id, exc)
        return False


def recipient_of(row: asyncpg.Record) -> str:
    """Which Discord account receives this participant's assignment.

    Normally the participant themselves. For someone entered through "register
    dùm" it is the member who registered them, since the participant has no
    Discord account to message.
    """
    return row["registered_by"] or row["user_id"]


async def _resolve_users(
    bot: discord.Client, discord_ids: List[str]
) -> Tuple[Dict[str, discord.User], List[str]]:
    """Fetch a User object per Discord id. Missing accounts are unreachable."""
    users: Dict[str, discord.User] = {}
    missing: List[str] = []
    for user_id in discord_ids:
        user = bot.get_user(int(user_id))
        if user is None:
            try:
                user = await bot.fetch_user(int(user_id))
            except (discord.HTTPException, ValueError):
                log.warning("Could not resolve user %s", user_id)
                missing.append(user_id)
                continue
        users[user_id] = user
    return users, missing


async def run_exchange(
    bot: discord.Client,
    db: Database,
    game: asyncpg.Record,
    edition: Edition,
    participants: List[asyncpg.Record],
) -> ExchangeResult:
    """Match everyone and deliver the assignments, or change nothing."""
    game_id = game["id"]
    by_id = {row["user_id"]: row for row in participants}

    # Everyone who has to be DM'd. A registrar appears once even if they
    # entered several people, and is checked once in the preflight.
    recipients: List[str] = []
    for row in participants:
        target = recipient_of(row)
        if target not in recipients:
            recipients.append(target)

    users, missing = await _resolve_users(bot, recipients)
    if missing:
        return ExchangeResult(ok=False, unreachable=missing)

    # ---- 1. Preflight: prove every DM actually goes through --------------
    probes: List[discord.Message] = []
    unreachable: List[str] = []
    for user_id, user in users.items():
        message = await _send_dm(user, content=edition.copy.preflight_dm)
        if message is None:
            unreachable.append(user_id)
        else:
            probes.append(message)
        await asyncio.sleep(SEND_DELAY_SECONDS)

    if unreachable:
        log.info(
            "Game %s aborted in preflight: %d unreachable", game_id, len(unreachable)
        )
        for message in probes:
            await _delete_quietly(message)
        return ExchangeResult(ok=False, unreachable=unreachable)

    # ---- 2. Draw and commit in one database transaction ------------------
    try:
        assignments = build_assignments(
            [row["user_id"] for row in participants], edition.match_strategy
        )
    except MatchError as exc:
        for message in probes:
            await _delete_quietly(message)
        return ExchangeResult(ok=False, error=str(exc))

    try:
        await queries.commit_start(db, game_id, assignments)
    except Exception as exc:  # noqa: BLE001 - reported to the host verbatim
        log.exception("Failed to commit assignments for game %s", game_id)
        for message in probes:
            await _delete_quietly(message)
        return ExchangeResult(ok=False, error=f"Database error: {exc}")

    # ---- 3. Deliver ------------------------------------------------------
    givers_by_receiver = santa_of(assignments)
    sent: List[discord.Message] = []
    failed: List[str] = []

    for giver_id, receiver_id in assignments.items():
        giver_row = by_id[giver_id]
        target_row = by_id[receiver_id]

        # Answers the reader's own santa wrote for them (TO_TARGET fields).
        santa_note = None
        if edition.target_fields:
            santa_id = givers_by_receiver.get(giver_id)
            if santa_id and santa_id in by_id:
                santa_note = queries.participant_answers(by_id[santa_id])

        # A proxy's assignment goes to their registrar as its own message,
        # worded so it cannot be confused with the registrar's own.
        on_behalf_of = (
            giver_row["display_name"] if giver_row["registered_by"] else None
        )
        recipient_id = recipient_of(giver_row)

        embed = ui.build_assignment_embed(
            edition, target_row, santa_note, on_behalf_of=on_behalf_of
        )
        content = (
            edition.copy.proxy_dm_intro.format(name=on_behalf_of)
            if on_behalf_of
            else None
        )
        message = await _send_dm(users[recipient_id], content=content, embed=embed)
        if message is None:
            failed.append(recipient_id)
            break

        sent.append(message)
        await queries.log_delivery(
            db,
            game_id,
            giver_id,
            recipient_id,
            str(message.channel.id),
            str(message.id),
        )
        await asyncio.sleep(SEND_DELAY_SECONDS)

    if not failed:
        log.info("Game %s delivered to %d participants", game_id, len(sent))
        return ExchangeResult(ok=True, delivered=len(sent))

    # ---- 4. Compensate: unsend everything, reopen the lobby --------------
    log.warning(
        "Game %s failed after commit (%d sent, %d failed) — rolling back",
        game_id,
        len(sent),
        len(failed),
    )
    deleted_all = True
    for message in sent:
        deleted_all &= await _delete_quietly(message)
    # The probes promised an assignment that is no longer coming.
    for message in probes:
        await _delete_quietly(message)

    rolled_back = deleted_all
    try:
        await queries.rollback_start(db, game_id)
    except Exception:  # noqa: BLE001 - logged; host is told the rollback failed
        log.exception("Rollback failed for game %s", game_id)
        rolled_back = False

    return ExchangeResult(
        ok=False, failed=failed, rolled_back=rolled_back, delivered=0
    )
