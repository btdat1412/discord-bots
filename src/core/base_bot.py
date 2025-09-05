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

    # ---------- Lifecycle ----------
    async def on_ready(self):
        log.info(
            "Bot connected as %s (id=%s), latency=%.2fms",
            self.user,
            self.user.id if self.user else "?",
            self.latency * 1000,
        )

    # ---------- Decorators ----------
    def command(self, name: str, **kwargs):
        def decorator(func):
            @wraps(func)
            async def wrapper(ctx, *args, **kw):
                return await func(ctx, *args, **kw)

            return super().command(name=name, **kwargs)(wrapper)

        return decorator

    def slash_command(self, name: str, description: str):
        def decorator(func):
            @app_commands.command(name=name, description=description)
            async def wrapper(interaction: discord.Interaction, *args, **kw):
                return await func(interaction, *args, **kw)

            self.tree.add_command(wrapper)
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
