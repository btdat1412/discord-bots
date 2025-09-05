from typing import List
from dataclasses import dataclass


@dataclass
class IntentsCfg:
    guilds: bool = True
    members: bool = False
    messages: bool = True
    message_content: bool = True
    reactions: bool = True


@dataclass
class BotCfg:
    name: str
    token: str
    intents: IntentsCfg
    cogs: List[str]


BOT_CONFIGS = [
    BotCfg(
        name="hello",
        token="YOUR_DISCORD_BOT_TOKEN_HERE",
        intents=IntentsCfg(
            guilds=True,
            members=False,
            messages=True,
            message_content=True,
            reactions=True,
        ),
        cogs=["src.bots.example_bot"],
    )
]


def get_bot_configs() -> List[BotCfg]:
    return BOT_CONFIGS
