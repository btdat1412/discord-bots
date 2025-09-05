import discord

from src.core.base_bot import BaseBot

"""Example Bot"""


class ExampleBot(BaseBot):

    def setup(self):
        self.register_commands()
        self.register_slash_commands()
        self.register_events()

    def register_commands(self):
        """Register all regular commands"""

        @self.command("serverinfo")
        async def server_info(self, ctx):
            if not ctx.guild:
                await self.send_message(
                    ctx.channel, "❌ This command can only be used in a server!"
                )
                return

            info = await self.get_guild_info(ctx.guild)

            embed = self.create_embed(title=f"📊 {ctx.guild.name} Server Info")
            embed.add_field(name="Owner", value=info["owner"], inline=True)
            embed.add_field(name="Members", value=info["member_count"], inline=True)
            embed.add_field(
                name="Created",
                value=info["created_at"].strftime("%Y-%m-%d"),
                inline=True,
            )
            embed.add_field(name="Boost Level", value=info["boost_level"], inline=True)
            embed.add_field(name="Boost Count", value=info["boost_count"], inline=True)
            embed.add_field(name="Channels", value=info["channels"], inline=True)
            embed.add_field(name="Roles", value=info["roles"], inline=True)
            embed.add_field(name="Emojis", value=info["emojis"], inline=True)
            embed.add_field(
                name="Features",
                value=", ".join(info["features"]) if info["features"] else "None",
                inline=False,
            )

            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            await self.send_message(ctx.channel, embed=embed)

        @self.command("userinfo")
        async def user_info(self, ctx, member: discord.Member = None):
            """Display user information"""
            member = member or ctx.author

            embed = self.create_embed(title=f"👤 {member.display_name}")
            embed.add_field(name="Username", value=str(member), inline=True)
            embed.add_field(name="ID", value=member.id, inline=True)
            embed.add_field(
                name="Joined Server",
                value=(
                    member.joined_at.strftime("%Y-%m-%d")
                    if member.joined_at
                    else "Unknown"
                ),
                inline=True,
            )
            embed.add_field(
                name="Account Created",
                value=member.created_at.strftime("%Y-%m-%d"),
                inline=True,
            )
            embed.add_field(
                name="Status", value=str(member.status).title(), inline=True
            )
            embed.add_field(
                name="Top Role",
                value=(
                    member.top_role.mention if hasattr(member, "top_role") else "None"
                ),
                inline=True,
            )

            if member.avatar:
                embed.set_thumbnail(url=member.avatar.url)

            await self.send_message(ctx.channel, embed=embed)
