"""Discord components. Buttons and the join modal are built from the edition.

Lobby buttons carry the game id inside their ``custom_id`` and the views use
``timeout=None``, so the bot can re-arm every open lobby after a restart (see
``SecretSantaBot.restore_open_lobbies``).
"""

import logging
from typing import TYPE_CHECKING, Dict, List

import asyncpg
import discord

from . import queries
from .models import MAX_FORM_FIELDS, Edition, Field, FieldStyle, SelectField

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from .bot import SecretSantaBot

log = logging.getLogger(__name__)

PREFIX = "santa"


def custom_id(action: str, game_id: int, *extra) -> str:
    return ":".join([PREFIX, action, str(game_id), *(str(e) for e in extra)])


def _build_component(field: Field) -> discord.ui.Item:
    """Turn one edition field into the matching modal component."""
    if isinstance(field, SelectField):
        return discord.ui.Select(
            placeholder=field.placeholder[:150] or None,
            required=field.required,
            min_values=1 if field.required else 0,
            max_values=1,
            options=[
                discord.SelectOption(label=option[:100], value=option[:100])
                for option in field.options
            ],
        )
    return discord.ui.TextInput(
        placeholder=field.placeholder[:100] or None,
        required=field.required,
        max_length=field.max_length,
        style=(
            discord.TextStyle.paragraph
            if field.style is FieldStyle.PARAGRAPH
            else discord.TextStyle.short
        ),
    )


def _value_of(item: discord.ui.Item) -> str:
    """Read back what the participant entered or picked."""
    if isinstance(item, discord.ui.Select):
        return item.values[0].strip() if item.values else ""
    return (item.value or "").strip()


# ------------------------------------------------------------------ modal ----


class JoinModal(discord.ui.Modal):
    """The join form, one component per field in the edition.

    Every component is wrapped in a :class:`discord.ui.Label`, which is what
    allows a dropdown (and not only text inputs) inside a modal.
    """

    def __init__(self, santa: "SecretSantaBot", game_id: int, edition: Edition):
        super().__init__(title=edition.modal_title[:45], timeout=600)
        self.santa = santa
        self.game_id = game_id
        self.edition = edition
        self._inputs: Dict[str, discord.ui.Item] = {}

        for field in edition.form:
            component = _build_component(field)
            self._inputs[field.key] = component
            self.add_item(
                discord.ui.Label(
                    text=field.label[:45],
                    description=(field.description or None) and field.description[:100],
                    component=component,
                )
            )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = {key: _value_of(item) for key, item in self._inputs.items()}
        await self.santa.handle_join_submit(interaction, self.game_id, answers)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        log.exception("Join modal failed for game %s", self.game_id, exc_info=error)
        message = self.edition.copy.form_error
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


# ------------------------------------------------------------------ lobby ----


class LobbyView(discord.ui.View):
    """Join / View / Start buttons on the lobby message. Never times out."""

    def __init__(
        self,
        santa: "SecretSantaBot",
        game_id: int,
        edition: Edition,
        show_start: bool,
    ):
        super().__init__(timeout=None)
        self.santa = santa
        self.game_id = game_id
        self.edition = edition

        join = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label=edition.join_button_label,
            emoji="🔄",
            custom_id=custom_id("join", game_id),
        )
        join.callback = self._on_join
        self.add_item(join)

        view_participants = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=edition.copy.view_button_label,
            emoji="👀",
            custom_id=custom_id("view", game_id),
        )
        view_participants.callback = self._on_view
        self.add_item(view_participants)

        register_for = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=edition.copy.proxy_button_label,
            emoji="📮",
            custom_id=custom_id("proxy", game_id),
        )
        register_for.callback = self._on_proxy
        self.add_item(register_for)

        if show_start:
            start = discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label=edition.start_button_label,
                emoji="🔒",
                custom_id=custom_id("start", game_id),
            )
            start.callback = self._on_start
            self.add_item(start)

    async def _on_join(self, interaction: discord.Interaction) -> None:
        await self.santa.handle_join_click(interaction, self.game_id)

    async def _on_view(self, interaction: discord.Interaction) -> None:
        await self.santa.handle_view_participants(interaction, self.game_id, page=1)

    async def _on_proxy(self, interaction: discord.Interaction) -> None:
        await self.santa.handle_proxy_click(interaction, self.game_id)

    async def _on_start(self, interaction: discord.Interaction) -> None:
        await self.santa.handle_start_click(interaction, self.game_id)


class CompletedView(discord.ui.View):
    """What the lobby message turns into once the game has been played."""

    def __init__(self, santa: "SecretSantaBot", game_id: int, edition: Edition):
        super().__init__(timeout=None)
        self.santa = santa
        self.game_id = game_id
        self.edition = edition

        view_participants = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=edition.copy.view_button_label,
            emoji="👀",
            custom_id=custom_id("view", game_id),
        )
        view_participants.callback = self._on_view
        self.add_item(view_participants)

    async def _on_view(self, interaction: discord.Interaction) -> None:
        await self.santa.handle_view_participants(interaction, self.game_id, page=1)


# ------------------------------------------------------------- pagination ----


class ParticipantsView(discord.ui.View):
    """Prev/Next on the ephemeral participants list."""

    def __init__(
        self,
        santa: "SecretSantaBot",
        game_id: int,
        edition: Edition,
        page: int,
        total_pages: int,
    ):
        super().__init__(timeout=300)
        self.santa = santa
        self.game_id = game_id
        self.page = page

        previous = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=edition.copy.prev_page,
            disabled=page <= 1,
            custom_id=custom_id("page", game_id, page - 1),
        )
        previous.callback = self._go_previous
        self.add_item(previous)

        nxt = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=edition.copy.next_page,
            disabled=page >= total_pages,
            custom_id=custom_id("page", game_id, page + 1),
        )
        nxt.callback = self._go_next
        self.add_item(nxt)

    async def _go_previous(self, interaction: discord.Interaction) -> None:
        await self.santa.handle_view_participants(
            interaction, self.game_id, page=self.page - 1, edit=True
        )

    async def _go_next(self, interaction: discord.Interaction) -> None:
        await self.santa.handle_view_participants(
            interaction, self.game_id, page=self.page + 1, edit=True
        )


# ----------------------------------------------------------------- opt-in ----


class OptInView(discord.ui.View):
    """Private / Public choice shown right after joining.

    ``target_user_id`` is the participant the choice applies to — the clicker
    themselves, or a proxy they just registered.
    """

    def __init__(
        self,
        santa: "SecretSantaBot",
        game_id: int,
        edition: Edition,
        target_user_id: str,
    ):
        super().__init__(timeout=300)
        self.santa = santa
        self.game_id = game_id
        self.target_user_id = target_user_id

        private = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=edition.copy.opt_in_private_label,
            custom_id=custom_id("optin", game_id, 0),
        )
        private.callback = self._make_handler(False)
        self.add_item(private)

        public = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label=edition.copy.opt_in_public_label,
            custom_id=custom_id("optin", game_id, 1),
        )
        public.callback = self._make_handler(True)
        self.add_item(public)

    def _make_handler(self, public: bool):
        async def handler(interaction: discord.Interaction) -> None:
            await self.santa.handle_opt_in(
                interaction, self.game_id, public, self.target_user_id
            )

        return handler


# ------------------------------------------------------------------ proxy ----


class ProxyModal(discord.ui.Modal):
    """The join form plus a name box, filled in on someone else's behalf."""

    NAME_KEY = "__proxy_name__"

    def __init__(self, santa: "SecretSantaBot", game_id: int, edition: Edition):
        super().__init__(title=edition.copy.proxy_modal_title[:45], timeout=600)
        self.santa = santa
        self.game_id = game_id
        self.edition = edition
        self._inputs: Dict[str, discord.ui.Item] = {}

        copy = edition.copy
        name_input = discord.ui.TextInput(
            placeholder=copy.proxy_name_placeholder[:100] or None,
            required=True,
            max_length=80,
            style=discord.TextStyle.short,
        )
        self._inputs[self.NAME_KEY] = name_input
        self.add_item(
            discord.ui.Label(text=copy.proxy_name_label[:45], component=name_input)
        )

        # A modal fits MAX_FORM_FIELDS components and the name box takes one,
        # so a full-length form loses its last field here.
        room = MAX_FORM_FIELDS - 1
        if len(edition.form) > room:
            log.warning(
                "Edition %s has %d fields; the register-dùm form can only show "
                "%d, so %s will not be asked",
                edition.key,
                len(edition.form),
                room,
                [f.key for f in edition.form[room:]],
            )
        for field in edition.form[:room]:
            component = _build_component(field)
            self._inputs[field.key] = component
            self.add_item(
                discord.ui.Label(
                    text=field.label[:45],
                    description=(field.description or None) and field.description[:100],
                    component=component,
                )
            )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = {key: _value_of(item) for key, item in self._inputs.items()}
        name = answers.pop(self.NAME_KEY, "").strip()
        await self.santa.handle_proxy_submit(
            interaction, self.game_id, name, answers
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        log.exception("Proxy modal failed for game %s", self.game_id, exc_info=error)
        message = self.edition.copy.form_error
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class ProxyPanelView(discord.ui.View):
    """Ephemeral panel: add another person, or remove one already entered."""

    MAX_REMOVE_BUTTONS = 4

    def __init__(
        self,
        santa: "SecretSantaBot",
        game_id: int,
        edition: Edition,
        proxies: List[asyncpg.Record],
    ):
        super().__init__(timeout=300)
        self.santa = santa
        self.game_id = game_id
        self.edition = edition

        add = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label=edition.copy.proxy_add_button,
            custom_id=custom_id("proxyadd", game_id),
        )
        add.callback = self._on_add
        self.add_item(add)

        for row in proxies[: self.MAX_REMOVE_BUTTONS]:
            remove = discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label=edition.copy.proxy_remove_button.format(
                    name=row["display_name"]
                )[:80],
                emoji="🗑️",
                custom_id=custom_id("proxydel", game_id, row["user_id"]),
            )
            remove.callback = self._make_remove(row["user_id"])
            self.add_item(remove)

    async def _on_add(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            ProxyModal(self.santa, self.game_id, self.edition)
        )

    def _make_remove(self, user_id: str):
        async def handler(interaction: discord.Interaction) -> None:
            await self.santa.handle_proxy_remove(
                interaction, self.game_id, user_id
            )

        return handler


def build_lobby_view(
    santa: "SecretSantaBot",
    game: asyncpg.Record,
    edition: Edition,
    participant_count: int,
) -> discord.ui.View:
    """The right view for a game's current state."""
    if game["state"] != queries.STATE_OPEN:
        return CompletedView(santa, game["id"], edition)
    return LobbyView(
        santa,
        game["id"],
        edition,
        show_start=participant_count >= edition.min_participants,
    )
