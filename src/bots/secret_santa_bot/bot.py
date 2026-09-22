"""Secret Santa bot — commands, interaction handlers, lobby bookkeeping."""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from src.shared.database import Database

from . import queries, ui, views
from .editions import EDITIONS, get_edition, latest_edition, sorted_editions
from .exchange import run_exchange
from .models import Edition

log = logging.getLogger(__name__)

DB_OFFLINE = "❌ Database của Secret Santa đang không kết nối được."
GAME_GONE = "❌ Game này không còn nữa."
NOT_HOST = "🔒 **Access Denied**: Nào đừng có phá"
GUILD_ONLY = "❌ Lệnh này chạy trong server, không chạy trong DM."
CREATE_FAILED = "❌ Tạo game không được. Thử lại nhé."
UNKNOWN_EDITION = "❌ Không có edition `{key}`."
NO_ASSIGNMENT_ON_RECORD = "❌ Bạn chưa có phần nào trong game đã xong ở server này."
DM_LOOKUP_NONE = (
    "Mình chưa thấy bạn có phần nào ở ván nào đã xong cả.\n"
    "Nếu ván chưa bắt đầu thì chờ chủ xị bấm bắt đầu nha."
)
DM_COOLDOWN_SECONDS = 5.0
EDITION_UNINSTALLED = (
    "❌ Game #{game_id} chơi bằng edition `{key}`, edition này không còn "
    "trong bot nữa."
)


class SecretSantaBot:
    """Holds the bot wiring. One instance per bot process."""

    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
        # One lock per game so a double-clicked Start button cannot draw twice.
        self._start_locks: Dict[int, asyncio.Lock] = {}
        self._dm_cooldown: Dict[str, float] = {}
        self._register_commands()

    # ------------------------------------------------------------------ #
    #  Slash commands                                                      #
    # ------------------------------------------------------------------ #

    def _register_commands(self) -> None:
        edition_choices = [
            app_commands.Choice(name=f"{e.year} — {e.command_description}", value=e.key)
            for e in sorted_editions()
        ]

        @app_commands.command(
            name="secret-santa", description="Mở một ván Secret Santa"
        )
        @app_commands.describe(
            edition="Chơi theo luật năm nào (mặc định: năm hiện tại)"
        )
        @app_commands.choices(edition=edition_choices)
        async def secret_santa(
            interaction: discord.Interaction,
            edition: Optional[app_commands.Choice[str]] = None,
        ):
            await self._do_open_lobby(
                interaction, edition.value if edition else None
            )

        self.bot.tree.add_command(secret_santa)

        @self.bot.slash_command(
            name="santa-history",
            description="Các ván Secret Santa đã chơi ở server này",
        )
        async def santa_history(interaction: discord.Interaction):
            await self._do_history(interaction)

        @self.bot.slash_command(
            name="santa-my-assignment",
            description="Xem lại phần của bạn ở ván vừa xong",
        )
        async def santa_my_assignment(interaction: discord.Interaction):
            await self._do_resend_assignment(interaction)

    # ------------------------------------------------------------------ #
    #  Command bodies                                                      #
    # ------------------------------------------------------------------ #

    async def _do_open_lobby(
        self, interaction: discord.Interaction, edition_key: Optional[str]
    ) -> None:
        if not await self._require_db(interaction):
            return
        if interaction.guild is None:
            await interaction.response.send_message(
                GUILD_ONLY, ephemeral=True
            )
            return

        edition = get_edition(edition_key) if edition_key else latest_edition()
        if edition is None:
            await interaction.response.send_message(
                UNKNOWN_EDITION.format(key=edition_key), ephemeral=True
            )
            return

        embed = ui.build_lobby_embed(edition, 0, str(interaction.user.id))
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()

        try:
            game = await queries.create_game(
                self.db,
                edition.key,
                str(interaction.guild_id),
                str(interaction.channel_id),
                str(message.id),
                str(interaction.user.id),
            )
        except Exception:
            log.exception("Failed to create game")
            await interaction.edit_original_response(
                content=CREATE_FAILED,
                embed=None,
                view=None,
            )
            return

        view = views.LobbyView(self, game["id"], edition, show_start=False)
        await interaction.edit_original_response(view=view)
        self.bot.add_view(view, message_id=message.id)
        log.info(
            "Opened game %s (edition %s) in guild %s",
            game["id"],
            edition.key,
            interaction.guild_id,
        )

    async def _do_history(self, interaction: discord.Interaction) -> None:
        if not await self._require_db(interaction):
            return
        if interaction.guild is None:
            await interaction.response.send_message(
                GUILD_ONLY, ephemeral=True
            )
            return

        rows = await queries.get_guild_games(self.db, str(interaction.guild_id))
        titles = {key: edition.title for key, edition in EDITIONS.items()}
        embed = ui.build_history_embed(interaction.guild.name, rows, titles)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _assignment_embeds(
        self, user_id: str, guild_id: Optional[str]
    ) -> Tuple[List[discord.Embed], Optional[Edition]]:
        """Every assignment ``user_id`` is entitled to see from their latest
        finished game: their own, plus one per person they registered dùm.

        Returns an empty list when there is nothing on record.
        """
        game = await queries.latest_completed_game_for_user(
            self.db, user_id, guild_id
        )
        if game is None:
            return [], None

        edition = get_edition(game["edition_key"])
        if edition is None:
            log.warning(
                "Game %s uses uninstalled edition %s",
                game["id"],
                game["edition_key"],
            )
            return [], None

        participants = await queries.get_participants(self.db, game["id"])
        by_id = {row["user_id"]: row for row in participants}

        def santa_note_for(giver_id: str):
            """TO_TARGET answers written by whoever gifts ``giver_id``."""
            if not edition.target_fields:
                return None
            for row in participants:
                if row["assigned_to"] == giver_id:
                    return queries.participant_answers(row)
            return None

        embeds = []
        for row in participants:
            if row["user_id"] != user_id and row["registered_by"] != user_id:
                continue
            target = by_id.get(row["assigned_to"])
            if target is None:
                continue
            embeds.append(
                ui.build_assignment_embed(
                    edition,
                    target,
                    santa_note_for(row["user_id"]),
                    on_behalf_of=(
                        row["display_name"] if row["registered_by"] else None
                    ),
                )
            )
        return embeds, edition

    async def _do_resend_assignment(self, interaction: discord.Interaction) -> None:
        if not await self._require_db(interaction):
            return

        embeds, _ = await self._assignment_embeds(
            str(interaction.user.id),
            str(interaction.guild_id) if interaction.guild else None,
        )
        if not embeds:
            await interaction.response.send_message(
                NO_ASSIGNMENT_ON_RECORD, ephemeral=True
            )
            return

        await interaction.response.send_message(embeds=embeds, ephemeral=True)

    async def handle_dm_lookup(self, message: discord.Message) -> None:
        """Reply to any DM with the sender's own assignment.

        Slash commands are synced per guild, so they do not exist in DMs. A
        plain message is the one thing that always works there — and it needs
        no message content, only the fact that a DM arrived.
        """
        if not self.db.ready:
            await message.channel.send(DB_OFFLINE)
            return

        user_id = str(message.author.id)
        now = time.monotonic()
        last = self._dm_cooldown.get(user_id)
        # No default timestamp here: monotonic() starts near zero, so a 0.0
        # default would swallow every DM for the bot's first few seconds.
        if last is not None and now - last < DM_COOLDOWN_SECONDS:
            return
        self._dm_cooldown[user_id] = now

        embeds, edition = await self._assignment_embeds(user_id, None)
        if not embeds:
            await message.channel.send(DM_LOOKUP_NONE)
            return

        await message.channel.send(edition.copy.dm_lookup_intro, embeds=embeds)

    # ------------------------------------------------------------------ #
    #  Button / modal handlers                                             #
    # ------------------------------------------------------------------ #

    async def handle_join_click(
        self, interaction: discord.Interaction, game_id: int
    ) -> None:
        """Join / Leave toggle."""
        context = await self._load(interaction, game_id)
        if context is None:
            return
        game, edition = context

        if game["state"] != queries.STATE_OPEN:
            await interaction.response.send_message(
                edition.copy.already_played, ephemeral=True
            )
            return

        user_id = str(interaction.user.id)
        if await queries.is_participant(self.db, game_id, user_id):
            await queries.remove_participant(self.db, game_id, user_id)
            await interaction.response.send_message(
                edition.copy.left_ok, ephemeral=True
            )
            await self._refresh_lobby(game, edition)
            return

        await interaction.response.send_modal(
            views.JoinModal(self, game_id, edition)
        )

    async def handle_join_submit(
        self,
        interaction: discord.Interaction,
        game_id: int,
        answers: Dict[str, str],
    ) -> None:
        context = await self._load(interaction, game_id)
        if context is None:
            return
        game, edition = context

        if game["state"] != queries.STATE_OPEN:
            await interaction.response.send_message(
                edition.copy.already_played, ephemeral=True
            )
            return

        member = interaction.user
        server_name = getattr(member, "nick", None) or member.display_name
        await queries.upsert_participant(
            self.db,
            game_id,
            str(member.id),
            member.name,
            server_name,
            member.display_avatar.replace(size=64).url,
            answers,
        )

        await interaction.response.send_message(
            edition.copy.joined_ok, ephemeral=True
        )
        await self._refresh_lobby(game, edition)

        if edition.has_opt_in:
            await interaction.followup.send(
                embed=ui.build_opt_in_embed(edition),
                view=views.OptInView(self, game_id, edition, str(member.id)),
                ephemeral=True,
            )

    async def handle_opt_in(
        self,
        interaction: discord.Interaction,
        game_id: int,
        public: bool,
        target_user_id: str,
    ) -> None:
        context = await self._load(interaction, game_id)
        if context is None:
            return
        _, edition = context

        await queries.set_public_opt_in(self.db, game_id, target_user_id, public)
        copy = edition.copy
        await interaction.response.send_message(
            copy.opt_in_saved.format(
                visibility=(
                    copy.opt_in_public_word if public else copy.opt_in_private_word
                )
            ),
            ephemeral=True,
        )

    # ---------- Register dùm ----------

    async def handle_proxy_click(
        self, interaction: discord.Interaction, game_id: int
    ) -> None:
        """Open the panel for people this member entered on someone's behalf.

        First time round there is nothing to manage, so the form opens straight
        away instead of showing an empty list.
        """
        context = await self._load(interaction, game_id)
        if context is None:
            return
        game, edition = context

        if game["state"] != queries.STATE_OPEN:
            await interaction.response.send_message(
                edition.copy.already_played, ephemeral=True
            )
            return

        proxies = await queries.get_proxies_by(
            self.db, game_id, str(interaction.user.id)
        )
        if not proxies:
            await interaction.response.send_modal(
                views.ProxyModal(self, game_id, edition)
            )
            return

        await interaction.response.send_message(
            embed=ui.build_proxy_panel_embed(edition, proxies),
            view=views.ProxyPanelView(self, game_id, edition, proxies),
            ephemeral=True,
        )

    async def handle_proxy_submit(
        self,
        interaction: discord.Interaction,
        game_id: int,
        name: str,
        answers: Dict[str, str],
    ) -> None:
        context = await self._load(interaction, game_id)
        if context is None:
            return
        game, edition = context
        copy = edition.copy

        if game["state"] != queries.STATE_OPEN:
            await interaction.response.send_message(
                copy.already_played, ephemeral=True
            )
            return

        if not name:
            await interaction.response.send_message(
                copy.proxy_name_required, ephemeral=True
            )
            return

        proxy_id = queries.new_proxy_id()
        await queries.upsert_participant(
            self.db,
            game_id,
            proxy_id,
            name,
            name,
            "",
            answers,
            registered_by=str(interaction.user.id),
        )

        await interaction.response.send_message(
            copy.proxy_registered_ok.format(name=name), ephemeral=True
        )
        await self._refresh_lobby(game, edition)

        if edition.has_opt_in:
            await interaction.followup.send(
                embed=ui.build_opt_in_embed(edition),
                view=views.OptInView(self, game_id, edition, proxy_id),
                ephemeral=True,
            )

    async def handle_proxy_remove(
        self, interaction: discord.Interaction, game_id: int, proxy_id: str
    ) -> None:
        context = await self._load(interaction, game_id)
        if context is None:
            return
        game, edition = context
        copy = edition.copy

        if game["state"] != queries.STATE_OPEN:
            await interaction.response.send_message(
                copy.already_played, ephemeral=True
            )
            return

        row = await queries.get_participant(self.db, game_id, proxy_id)
        # Only the member who entered this person may remove them.
        if row is None or row["registered_by"] != str(interaction.user.id):
            await interaction.response.send_message(
                copy.proxy_gone, ephemeral=True
            )
            return

        await queries.remove_participant(self.db, game_id, proxy_id)
        proxies = await queries.get_proxies_by(
            self.db, game_id, str(interaction.user.id)
        )
        await interaction.response.edit_message(
            content=copy.proxy_removed.format(name=row["display_name"]),
            embed=ui.build_proxy_panel_embed(edition, proxies),
            view=views.ProxyPanelView(self, game_id, edition, proxies),
        )
        await self._refresh_lobby(game, edition)

    async def handle_view_participants(
        self,
        interaction: discord.Interaction,
        game_id: int,
        page: int,
        edit: bool = False,
    ) -> None:
        context = await self._load(interaction, game_id)
        if context is None:
            return
        _, edition = context

        participants = await queries.get_participants(self.db, game_id)
        embed, page = ui.build_participants_embed(edition, participants, page)
        total_pages = max(1, (len(participants) + ui.PAGE_SIZE - 1) // ui.PAGE_SIZE)
        view = (
            views.ParticipantsView(self, game_id, edition, page, total_pages)
            if total_pages > 1
            else None
        )

        if edit:
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(
                embed=embed, view=view, ephemeral=True
            )

    async def handle_start_click(
        self, interaction: discord.Interaction, game_id: int
    ) -> None:
        context = await self._load(interaction, game_id)
        if context is None:
            return
        game, edition = context

        if str(interaction.user.id) != game["host_id"]:
            await interaction.response.send_message(NOT_HOST, ephemeral=True)
            return

        lock = self._start_locks.setdefault(game_id, asyncio.Lock())
        if lock.locked():
            await interaction.response.send_message(
                edition.copy.draw_running, ephemeral=True
            )
            return

        # The draw sends one DM per participant, far longer than the 3 seconds
        # Discord allows for a reply, so acknowledge now and follow up later.
        await interaction.response.defer(ephemeral=True, thinking=True)

        async with lock:
            # Re-read inside the lock: the state may have changed while waiting.
            game = await queries.get_game(self.db, game_id)
            if game is None or game["state"] != queries.STATE_OPEN:
                await interaction.followup.send(
                    edition.copy.already_played, ephemeral=True
                )
                return

            participants = await queries.get_participants(self.db, game_id)
            if len(participants) < edition.min_participants:
                await interaction.followup.send(
                    edition.copy.not_enough.format(
                        needed=edition.min_participants,
                        count=len(participants),
                    ),
                    ephemeral=True,
                )
                return

            channel = interaction.channel
            if channel is not None:
                await channel.send(edition.copy.shuffling)

            result = await run_exchange(
                self.bot, self.db, game, edition, participants
            )

            if not result.ok:
                if channel is not None:
                    await channel.send(result.problem_report(edition))
                await interaction.followup.send(
                    edition.copy.start_failed_host, ephemeral=True
                )
                await self._refresh_lobby(game, edition)
                return

            game = await queries.get_game(self.db, game_id)
            await self._refresh_lobby(game, edition)
            if channel is not None:
                await channel.send(
                    edition.copy.started_channel.format(
                        title=edition.title, count=result.delivered
                    )
                )
            await interaction.followup.send(
                edition.copy.started_host.format(count=result.delivered),
                ephemeral=True,
            )

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    async def _require_db(self, interaction: discord.Interaction) -> bool:
        if self.db.ready:
            return True
        await interaction.response.send_message(DB_OFFLINE, ephemeral=True)
        return False

    async def _load(
        self, interaction: discord.Interaction, game_id: int
    ) -> Optional[tuple]:
        """Fetch the game and its edition, replying with an error if either is gone."""
        if not await self._require_db(interaction):
            return None

        game = await queries.get_game(self.db, game_id)
        if game is None:
            await interaction.response.send_message(GAME_GONE, ephemeral=True)
            return None

        edition = get_edition(game["edition_key"])
        if edition is None:
            await interaction.response.send_message(
                EDITION_UNINSTALLED.format(
                    game_id=game["id"], key=game["edition_key"]
                ),
                ephemeral=True,
            )
            return None

        return game, edition

    async def _refresh_lobby(
        self, game: asyncpg.Record, edition: Edition
    ) -> None:
        """Re-render the lobby message with the current count and buttons."""
        try:
            channel = self.bot.get_channel(int(game["channel_id"]))
            if channel is None:
                channel = await self.bot.fetch_channel(int(game["channel_id"]))
            message = await channel.fetch_message(int(game["message_id"]))
        except (discord.HTTPException, ValueError):
            log.warning("Lobby message for game %s is unreachable", game["id"])
            return

        count = await queries.count_participants(self.db, game["id"])
        if game["state"] == queries.STATE_OPEN:
            missing = edition.min_participants - count
            embed = ui.build_lobby_embed(
                edition,
                count,
                game["host_id"],
                min_needed=(
                    f"{missing} more participant(s) needed before the host can "
                    f"start."
                    if missing > 0
                    else None
                ),
            )
        else:
            embed = ui.build_completed_embed(edition, count, game["host_id"])

        view = views.build_lobby_view(self, game, edition, count)
        try:
            await message.edit(embed=embed, view=view)
        except discord.HTTPException:
            log.exception("Failed to update lobby message for game %s", game["id"])
            return
        self.bot.add_view(view, message_id=message.id)

    async def restore_open_lobbies(self) -> None:
        """Re-arm the buttons of every open lobby after a restart.

        Without this, persistent views are lost on restart and clicking a
        button on an old lobby does nothing.
        """
        if not self.db.ready:
            return
        try:
            games = await queries.get_open_games(self.db)
        except Exception:
            log.exception("Could not load open games")
            return

        restored = 0
        for game in games:
            edition = get_edition(game["edition_key"])
            if edition is None:
                continue
            count = await queries.count_participants(self.db, game["id"])
            view = views.build_lobby_view(self, game, edition, count)
            try:
                self.bot.add_view(view, message_id=int(game["message_id"]))
                restored += 1
            except ValueError:
                log.warning("Bad message id on game %s", game["id"])
        log.info("Restored buttons on %d open lobby/lobbies", restored)
