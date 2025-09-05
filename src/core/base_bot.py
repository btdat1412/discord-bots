# base.py
import logging
from functools import wraps
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)

"""Class for Helping Bot Creations"""


class BaseBot(commands.Bot):

    def __init__(self, prefix: str, intents: discord.Intents):
        super().__init__(command_prefix=prefix, intents=intents)
        self._commands_synced = False

    # ---------- Lifecycle ----------
    async def on_ready(self):
        await self._sync_commands_once()
        log.info(
            "Bot connected as %s (id=%s), latency=%.2fms",
            self.user,
            getattr(self.user, "id", "?"),
            self.latency * 1000,
        )

    # Handle Syncing the Commands when first enter Server
    async def _sync_commands_once(self):
        """Sync slash commands to Discord. Only runs once per bot instance."""
        if self._commands_synced:
            log.debug("Commands already synced, skipping")
            return

        try:
            commands = [cmd.name for cmd in self.tree.get_commands()]
            log.info("Syncing %d slash commands: %s", len(commands), commands)

            for g in self.guilds:
                try:
                    synced = await self.tree.sync(guild=discord.Object(id=g.id))
                    log.info(
                        "Synced %d commands to guild '%s' (id=%s)",
                        len(synced),
                        g.name,
                        g.id,
                    )
                except Exception as e:
                    log.error(
                        "Failed to sync commands to guild '%s' (id=%s): %s",
                        g.name,
                        g.id,
                        e,
                    )

            try:
                global_synced = await self.tree.sync()
                log.info("Synced %d commands globally", len(global_synced))
            except Exception as e:
                log.error("Failed to sync commands globally: %s", e)
                raise

            self._commands_synced = True
            log.info("Command sync completed successfully")
        except Exception:
            log.exception("Slash command sync failed")
            raise

    async def force_sync_commands(self):
        """Force re-sync of commands even if already synced. Useful for development."""
        self._commands_synced = False
        await self._sync_commands_once()

    @property
    def commands_synced(self) -> bool:
        """Check if commands have been synced to Discord."""
        return self._commands_synced

    # ---------- Decorators ----------

    # Register a Command with Prefix (like !ping)
    def command(self, name: str, **kwargs):
        def decorator(func):
            @wraps(func)
            async def wrapper(ctx, *args, **kw):
                return await func(ctx, *args, **kw)

            return commands.Bot.command(self, name=name, **kwargs)(wrapper)

        return decorator

    # Register a Slash Command (like /ping)
    def slash_command(self, name: str, description: str):
        def decorator(func):
            @app_commands.command(name=name, description=description)
            async def wrapper(interaction: discord.Interaction):
                return await func(interaction)

            self.tree.add_command(wrapper)
            log.info("Added slash command '%s' to command tree", name)
            return wrapper

        return decorator

    def event_listener(self, event_name: str):
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kw):
                return await func(*args, **kw)

            self.add_listener(wrapper, name=event_name)
            return wrapper

        return decorator

    # ---------- Utilities ----------
    # ---------- Contribute to this if you have time ----------
    async def send_embed(
        self,
        channel: discord.abc.Messageable,
        title: str,
        description: str,
        color: discord.Color = discord.Color.blurple(),
    ):
        embed = discord.Embed(title=title, description=description, color=color)
        return await channel.send(embed=embed)

    async def clear_messages(self, channel: discord.TextChannel, limit: int = 100):
        return await channel.purge(limit=limit)

    def stats(self):
        return {"latency_ms": round(self.latency * 1000, 2)}
