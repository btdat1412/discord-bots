"""Starting the exchange — all-or-nothing.

Discord has no transactions, so the closest honest equivalent is built here:

1. **Preflight** — send a short probe DM to everyone who has to be messaged.
   Opening a DM channel succeeds even for people who block DMs (this is what
   the old Go bot got wrong), so an actual send is the only proof the bot can
   reach someone. If anyone fails, the probes are deleted and the run stops
   before a single assignment exists.
2. **Deliver** — send the assignment DMs, remembering each message.
3. **Undo on failure** — delete every DM already sent. The database has not
   been touched at all, so there is nothing else to undo.
4. **Commit** — only once every DM has landed, write the assignments, the
   delivery log and the new game state in one database transaction.

Either everybody gets their assignment, or nobody does. The probe is what makes
that true even for the first person in the delivery order: without it, whoever
is early would receive an assignment that a later failure has to take back.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import asyncpg
import discord

from src.shared.database import Database

from . import queries, ui
from .matching import Blocked, MatchError, block_across, build_assignments, santa_of
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
    """Discord ids the bot could not DM. Delivery stops at the first one."""
    cleaned_up: bool = True
    """False when a DM the bot had already sent could not be deleted again,
    meaning somebody may have seen an assignment that no longer counts."""
    error: Optional[str] = None

    def problem_report(self, edition: Edition) -> str:
        """Channel message explaining why nobody received anything."""
        copy = edition.copy
        tail = "" if self.cleaned_up else f"\n\n{copy.cleanup_failed_note}"

        if self.unreachable:
            mentions = "\n".join(f"• <@{uid}>" for uid in self.unreachable)
            return (
                f"{copy.unreachable_title}\n{mentions}\n\n"
                f"{copy.unreachable_help}{tail}"
            )

        reason = self.error or "Lỗi lạ — coi log giùm."
        return copy.generic_failure.format(reason=reason) + tail


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


def exclusions_for(
    edition: Edition, participants: List[asyncpg.Record]
) -> Blocked:
    blocked: Blocked = {}
    for group in edition.exclusions:
        sides = []
        for root in group:
            side = [
                row["user_id"]
                for row in participants
                if row["user_id"] == root or row["registered_by"] == root
            ]
            if side:
                sides.append(side)
        if len(sides) > 1:
            block_across(sides, blocked)
    return blocked


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

    # Everyone who has to be DM'd. A member who registered several people
    # appears once per assignment they are responsible for, their own included.
    recipients: List[str] = []
    for row in participants:
        target = recipient_of(row)
        if target not in recipients:
            recipients.append(target)

    users, missing = await _resolve_users(bot, recipients)
    if missing:
        return ExchangeResult(ok=False, unreachable=missing)

    # ---- 1. Preflight: prove every DM goes through before drawing ---------
    probes: List[discord.Message] = []
    blocked: List[str] = []
    for user_id in recipients:
        message = await _send_dm(users[user_id], content=edition.copy.preflight_dm)
        if message is None:
            blocked.append(user_id)
        else:
            probes.append(message)
        await asyncio.sleep(SEND_DELAY_SECONDS)

    if blocked:
        log.info("Game %s aborted in preflight: %s unreachable", game_id, blocked)
        cleaned = True
        for message in probes:
            cleaned &= await _delete_quietly(message)
        return ExchangeResult(ok=False, unreachable=blocked, cleaned_up=cleaned)

    try:
        assignments = build_assignments(
            [row["user_id"] for row in participants],
            edition.match_strategy,
            exclusions_for(edition, participants),
        )
    except MatchError as exc:
        for message in probes:
            await _delete_quietly(message)
        return ExchangeResult(ok=False, error=str(exc))

    # ---- 2. Deliver, stopping the moment anyone cannot be reached ---------
    givers_by_receiver = santa_of(assignments)
    sent: List[discord.Message] = []
    deliveries: List[Tuple[str, str, str, str]] = []
    unreachable: List[str] = []

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
            unreachable.append(recipient_id)
            break

        sent.append(message)
        deliveries.append(
            (giver_id, recipient_id, str(message.channel.id), str(message.id))
        )
        await asyncio.sleep(SEND_DELAY_SECONDS)

    # ---- 3. Someone slipped through the preflight: unsend everything ------
    if unreachable:
        log.warning(
            "Game %s: %s passed the preflight but refused the assignment "
            "after %d delivered — undoing",
            game_id,
            unreachable,
            len(sent),
        )
        cleaned = True
        for message in sent + probes:
            cleaned &= await _delete_quietly(message)
        return ExchangeResult(ok=False, unreachable=unreachable, cleaned_up=cleaned)

    # ---- 4. Everyone has their DM: now it is safe to save -----------------
    try:
        await queries.commit_start(db, game_id, assignments, deliveries)
    except Exception as exc:  # noqa: BLE001 - reported to the host verbatim
        log.exception("Failed to commit assignments for game %s", game_id)
        cleaned = True
        for message in sent + probes:
            cleaned &= await _delete_quietly(message)
        return ExchangeResult(
            ok=False, error=f"Database error: {exc}", cleaned_up=cleaned
        )

    log.info("Game %s delivered to %d recipients", game_id, len(sent))
    return ExchangeResult(ok=True, delivered=len(sent))
