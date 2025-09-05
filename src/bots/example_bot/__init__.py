def setup(bot):
    @bot.command("ping")
    async def ping(ctx):
        await ctx.send("Pong! 🏓")
