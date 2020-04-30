import asyncio
from typing import Sequence

import psutil
from discord import Message, Member, User, Reaction
from discord.ext.commands import Context, Bot
from discord.utils import get

from src.constants import Emoji


def has_role(member, role: str):
    """Return whether the member has a role with this name."""

    return any(r.name == role for r in member.roles)


def start_time(self):
    return psutil.Process().create_time()


def setup(bot: Bot):
    pass
