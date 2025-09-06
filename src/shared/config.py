import os
from typing import List
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class IntentsCfg:
    guilds: bool = True
    members: bool = False
    messages: bool = True
    message_content: bool = False  # Privileged intent - set to False by default
    reactions: bool = True


@dataclass
class BotCfg:
    name: str
    token: str
    intents: IntentsCfg
    cogs: List[str]


BOT_CONFIGS = [
    BotCfg(
        name="ti-gia",
        token=os.getenv("TI_GIA_BOT_TOKEN", ""),
        intents=IntentsCfg(
            # intents = permissions of the bot
            guilds=True,
            members=False,
            messages=True,
            message_content=False,
            reactions=True,
        ),
        cogs=["src.bots.ti_gia_bot"],
    ),
]


def get_bot_configs() -> List[BotCfg]:
    return BOT_CONFIGS
