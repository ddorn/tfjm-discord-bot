import random

from discord.ext.commands import Cog, command, Context, Bot

from src.constants import *


class MiscCog(Cog, name="Divers"):
    @command(
        name="choose",
        usage='choix1 choix2 "choix 3"...',
        aliases=["choice", "choix", "ch"],
    )
    async def choose(self, ctx: Context, *args):
        """
        Choisit une option parmi tous les arguments.

        Pour les options qui contiennent une espace,
        il suffit de mettre des guillemets (`"`) autour.
        """

        choice = random.choice(args)
        await ctx.send(f"J'ai choisi... **{choice}**")

    @command(name="joke", aliases=["blague"], hidden=True)
    async def joke_cmd(self, ctx):
        with open(JOKES_FILE) as f:
            jokes = f.read().split("\n\n\n")

        msg = random.choice(jokes)
        await ctx.send(msg)


def setup(bot: Bot):
    bot.add_cog(MiscCog())
