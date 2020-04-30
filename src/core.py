import asyncio
import sys
from importlib import reload

import psutil
from discord import User, Message, Reaction
from discord.ext.commands import Bot


__all__ = ["CustomBot"]

from discord.utils import get

from src.constants import Emoji


class CustomBot(Bot):
    """
    This is the same as a discord bot except
    for class reloading and it provides hints
    for the type checker about the modules
    that are added by extensions.
    """

    def __str__(self):
        return f"{self.__class__.__name__}:{hex(id(self.__class__))} obj at {hex(id(self))}"

    def reload(self):
        cls = self.__class__
        module_name = cls.__module__
        old_module = sys.modules[module_name]

        print("Trying to reload the bot.")
        try:
            # del sys.modules[module_name]
            module = reload(old_module)
            self.__class__ = getattr(module, cls.__name__, cls)
        except:
            print("Could not reload the bot :/")
            raise
        print("The bot has reloaded !")

    async def wait_for_bin(bot: Bot, user: User, *msgs: Message, timeout=300):
        """Wait for timeout seconds for `user` to delete the messages."""

        msgs = list(msgs)

        assert msgs, "No messages in wait_for_bin"

        for m in msgs:
            await m.add_reaction(Emoji.BIN)

        def check(reaction: Reaction, u):
            return (
                user == u
                and any(m.id == reaction.message.id for m in msgs)
                and str(reaction.emoji) == Emoji.BIN
            )

        try:
            while msgs:
                reaction, u = await bot.wait_for(
                    "reaction_add", check=check, timeout=timeout
                )
                the_msg = get(msgs, id=reaction.message.id)
                await the_msg.delete()
                msgs.remove(the_msg)
        except asyncio.TimeoutError:
            pass

        for m in msgs:
            await m.clear_reaction(Emoji.BIN)
