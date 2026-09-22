"""Embed builders. Every string comes from the edition, nothing is hardcoded."""

from typing import Any, Dict, List, Optional, Tuple

import asyncpg
import discord

from .models import Edition, FormField
from .queries import participant_answers

# Discord embed limits.
EMBED_FIELD_LIMIT = 1024
EMBED_DESCRIPTION_LIMIT = 4096

# The participants list is paginated by character budget, not by a fixed
# number of people: five participants who each filled in 500-character answers
# overflow the description limit and Discord rejects the whole interaction.
PAGE_BUDGET = 3800
MAX_PER_PAGE = 10
ANSWER_PREVIEW = 150
"""Answers are trimmed in the list — the full text is in the assignment DM."""


def display_name(row: asyncpg.Record) -> str:
    """Server nickname with the account name in brackets, best effort."""
    server = row["display_name_server"]
    account = row["display_name"]
    if server:
        return f"{server} ({account})" if account else f"{server} ({row['user_id']})"
    return account or row["user_id"]


def _thumbnail(embed: discord.Embed, edition: Edition) -> discord.Embed:
    if edition.thumbnail_url:
        embed.set_thumbnail(url=edition.thumbnail_url)
    return embed


def _answer_text(field: FormField, answers: Dict[str, Any]) -> Optional[str]:
    """Rendered value for one field, or ``None`` when it should be skipped."""
    value = (answers.get(field.key) or "").strip()
    if not value:
        return field.empty_text
    return value[:EMBED_FIELD_LIMIT]


def _add_answers(
    embed: discord.Embed, fields: List[FormField], answers: Dict[str, Any]
) -> None:
    for field in fields:
        text = _answer_text(field, answers)
        if text:
            embed.add_field(name=field.heading(), value=text, inline=False)


# ----------------------------------------------------------------- lobby ----


def build_lobby_embed(
    edition: Edition,
    participant_count: int,
    host_id: str,
    min_needed: Optional[str] = None,
) -> discord.Embed:
    copy = edition.copy
    embed = discord.Embed(
        title=edition.title,
        description=edition.lobby_description,
        color=edition.lobby_color,
    )
    embed.add_field(
        name=copy.participants,
        value=copy.joined.format(count=participant_count),
        inline=True,
    )
    embed.add_field(name=copy.host, value=f"<@{host_id}>", inline=True)
    embed.add_field(
        name=copy.how_it_works, value=edition.how_it_works, inline=False
    )
    if min_needed:
        embed.add_field(name=copy.not_ready_label, value=min_needed, inline=False)
    embed.add_field(
        name=copy.important_label, value=copy.important_text, inline=False
    )
    embed.set_footer(text=edition.footer)
    return _thumbnail(embed, edition)


def build_completed_embed(
    edition: Edition, participant_count: int, host_id: str
) -> discord.Embed:
    copy = edition.copy
    embed = discord.Embed(
        title=copy.completed_title.format(title=edition.title),
        description=copy.completed_description,
        color=edition.completed_color,
    )
    embed.add_field(
        name=copy.participants,
        value=copy.joined.format(count=participant_count),
        inline=True,
    )
    embed.add_field(name=copy.host, value=f"<@{host_id}>", inline=True)
    embed.add_field(
        name=copy.status_label, value=copy.status_completed, inline=True
    )
    embed.set_footer(text=copy.completed_footer.format(footer=edition.footer))
    return _thumbnail(embed, edition)


# ---------------------------------------------------------- participants ----


def _preview(value: str) -> str:
    value = " ".join(value.split())
    if len(value) <= ANSWER_PREVIEW:
        return value
    return value[: ANSWER_PREVIEW - 1].rstrip() + "…"


def _participant_line(
    edition: Edition, row: asyncpg.Record, index: int
) -> str:
    answers = participant_answers(row)
    copy = edition.copy
    line = f"**{index}.** {display_name(row)}"
    if row["avatar_url"]:
        line += f" [🖼️]({row['avatar_url']})"
    if row["registered_by"]:
        marker = copy.proxy_list_marker.format(mention=f"<@{row['registered_by']}>")
        line += f" · *{marker}*"

    visible = list(edition.always_public_fields)
    if row["public_opt_in"]:
        visible += edition.opt_in_fields
    for field in visible:
        value = (answers.get(field.key) or "").strip()
        if value:
            line += f"\n     {field.heading()}: {_preview(value)}"
    return line


def paginate_participants(
    edition: Edition, participants: List[asyncpg.Record]
) -> List[List[str]]:
    """Split the rendered lines into pages that each fit in one embed.

    A page closes when adding the next participant would pass
    :data:`PAGE_BUDGET`, so no page can ever exceed Discord's description
    limit however much people wrote. Always returns at least one page.
    """
    pages: List[List[str]] = [[]]
    used = 0
    for index, row in enumerate(participants, 1):
        line = _participant_line(edition, row, index)
        # Hard cap one line on its own, so a single huge entry cannot
        # overflow a page by itself.
        line = line[:PAGE_BUDGET]
        cost = len(line) + 2  # the "\n\n" joining it to the previous line
        if pages[-1] and (used + cost > PAGE_BUDGET or len(pages[-1]) >= MAX_PER_PAGE):
            pages.append([])
            used = 0
        pages[-1].append(line)
        used += cost
    return pages


def build_participants_embed(
    edition: Edition, participants: List[asyncpg.Record], page: int
) -> Tuple[discord.Embed, int, int]:
    """Returns the embed, the clamped page number and the total page count."""
    copy = edition.copy
    embed = discord.Embed(title=copy.participants_title, color=edition.lobby_color)
    _thumbnail(embed, edition)

    if not participants:
        embed.description = copy.participants_empty
        return embed, 1, 1

    pages = paginate_participants(edition, participants)
    total_pages = len(pages)
    page = max(1, min(page, total_pages))

    embed.description = "\n\n".join(pages[page - 1])[:EMBED_DESCRIPTION_LIMIT]
    embed.set_footer(
        text=copy.participants_footer.format(
            page=page, pages=total_pages, total=len(participants)
        )
    )
    return embed, page, total_pages


# ------------------------------------------------------------ assignment ----


def build_assignment_embed(
    edition: Edition,
    target: asyncpg.Record,
    santa_note_answers: Optional[Dict[str, Any]] = None,
    on_behalf_of: Optional[str] = None,
) -> discord.Embed:
    """The DM a giver receives.

    ``santa_note_answers`` holds the answers of the participant who was
    assigned to gift *this* reader — only their ``TO_TARGET`` fields are shown.

    ``on_behalf_of`` is the name of a proxy participant. When set, this is the
    copy sent to whoever registered them, and the wording says so throughout so
    the registrar cannot mistake it for their own assignment.
    """
    copy = edition.copy
    if on_behalf_of:
        title = copy.proxy_dm_title.format(name=on_behalf_of)
        line = edition.proxy_assignment_line.format(
            name=on_behalf_of, target=display_name(target)
        )
        footer = copy.proxy_dm_footer.format(name=on_behalf_of)
    else:
        title = edition.assignment_title
        line = edition.assignment_line.format(target=display_name(target))
        footer = edition.assignment_footer

    embed = discord.Embed(
        title=title, description=line, color=edition.assignment_color
    )
    if target["avatar_url"]:
        embed.set_image(url=target["avatar_url"])

    _add_answers(embed, edition.santa_fields, participant_answers(target))

    if santa_note_answers:
        for field in edition.target_fields:
            text = _answer_text(field, santa_note_answers)
            if text:
                embed.add_field(
                    name=edition.santa_note_heading, value=text, inline=False
                )

    embed.set_footer(text=footer)
    return embed


# ---------------------------------------------------------------- opt-in ----


def build_opt_in_embed(edition: Edition) -> discord.Embed:
    copy = edition.copy
    embed = discord.Embed(
        title=copy.opt_in_title,
        description=edition.opt_in_prompt,
        color=0x9B59B6,
    )
    embed.add_field(
        name=copy.opt_in_private_label,
        value=copy.opt_in_private_text,
        inline=False,
    )
    embed.add_field(
        name=copy.opt_in_public_label,
        value=copy.opt_in_public_text,
        inline=False,
    )
    embed.set_footer(text=copy.opt_in_footer)
    return _thumbnail(embed, edition)


# ----------------------------------------------------------------- proxy ----


def build_proxy_panel_embed(
    edition: Edition, proxies: List[asyncpg.Record]
) -> discord.Embed:
    """Ephemeral panel listing the people this member registered."""
    copy = edition.copy
    embed = discord.Embed(
        title=copy.proxy_panel_title,
        description=copy.proxy_panel_description,
        color=edition.lobby_color,
    )
    if not proxies:
        embed.description = copy.proxy_panel_empty
        return _thumbnail(embed, edition)

    for index, row in enumerate(proxies, 1):
        answers = participant_answers(row)
        parts = []
        for field in edition.form:
            value = (answers.get(field.key) or "").strip()
            if value:
                parts.append(f"{field.heading()}: {value}")
        embed.add_field(
            name=f"{index}. {row['display_name']}",
            value="\n".join(parts) or "—",
            inline=False,
        )
    return _thumbnail(embed, edition)


# ---------------------------------------------------------------- history ----


def build_history_embed(
    guild_name: str, rows: List[asyncpg.Record], edition_titles: Dict[str, str]
) -> discord.Embed:
    embed = discord.Embed(
        title=f"📜 Các ván đã chơi — {guild_name}",
        color=0x9B59B6,
    )
    if not rows:
        embed.description = "Server này chưa chơi ván nào."
        return embed

    state_icon = {
        "OPEN": "🟢 đang mở",
        "COMPLETED": "🏁 đã xong",
        "CANCELLED": "🚫 đã huỷ",
    }
    for row in rows:
        title = edition_titles.get(row["edition_key"], row["edition_key"])
        when = row["created_at"].strftime("%d/%m/%Y")
        embed.add_field(
            name=f"#{row['id']} — {title}",
            value=(
                f"{state_icon.get(row['state'], row['state'])} • "
                f"{row['participant_count']} người • "
                f"chủ xị <@{row['host_id']}> • {when}"
            ),
            inline=False,
        )
    embed.set_footer(text="Mới nhất ở trên")
    return embed
