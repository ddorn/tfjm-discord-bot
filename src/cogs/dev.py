import code
from pprint import pprint

from discord.ext.commands import command, has_role, Bot
from discord.ext.commands import Cog

from src.constants import *


class DevCog(Cog, name="Dev tools"):
    def __init__(self, bot: Bot):
        self.bot = bot

    @command(name="interrupt")
    @has_role(Role.DEV)
    async def interrupt_cmd(self, ctx):
        """
        (dev) Ouvre une console là où un @dev m'a lancé. :warning:

        A utiliser en dernier recours:
         - le bot sera inactif pendant ce temps.
         - toutes les commandes seront executées à sa reprise.
        """

        await ctx.send(
            "J'ai été arrêté et une console interactive a été ouverte là où je tourne. "
            "Toutes les commandes rateront tant que cette console est ouverte.\n"
            "Soyez rapides, je déteste les opérations à coeur ouvert... :confounded:"
        )

        # Utility functions

        local = {
            **globals(),
            **locals(),
            "pprint": pprint,
            "_show": lambda o: print(*dir(o), sep="\n"),
            "__name__": "__console__",
            "__doc__": None,
        }

        code.interact(
            banner="Ne SURTOUT PAS FAIRE Ctrl+C !\n(TFJM² debugger)", local=local
        )
        await ctx.send("Tout va mieux !")

    @command(name="reload")
    @has_role(Role.DEV)
    async def reload_cmd(self, ctx, name):

        if name in ("dev", "teams", "tirages"):
            name = f"src.cogs.{name}"

        try:
            self.bot.reload_extension(name)
        except:
            await ctx.send(f":grimacing: **{name}** n'a pas pu être rechargée.")
            raise
        else:
            await ctx.send(f":tada: L'extension **{name}** a bien été rechargée.")


def setup(bot: Bot):
    bot.add_cog(DevCog(bot))
