from .ti_gia_bot import TiGiaBot


def setup(bot):
    bot.ti_gia_bot = TiGiaBot(bot)
