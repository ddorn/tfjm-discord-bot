#!/bin/python
import code
import random
import sys
import traceback
from pprint import pprint

import discord
from discord.ext import commands
from discord.ext.commands import Context

from src.cogs import TfjmHelpCommand
from src.constants import *
from src.errors import TfjmError, UnwantedCommand

bot = commands.Bot("!", help_command=TfjmHelpCommand())

# Variable globale qui contient les tirages.
tirages = {}


@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")


@bot.command(
    name="choose",
    usage='choix1 choix2 "choix 3"...',
    aliases=["choice", "choix", "ch"],
)
async def choose(ctx: Context, *args):
    """
    Choisit une option parmi tous les arguments.

    Pour les options qui contiennent une espace,
    il suffit de mettre des guillemets (`"`) autour.
    """

    choice = random.choice(args)
    await ctx.send(f"J'ai choisi... **{choice}**")


@bot.command(name="interrupt")
@commands.has_role(CNO_ROLE)
async def interrupt_cmd(ctx):
    """
    :warning: Ouvre une console là où un @dev m'a lancé. :warning:

    A utiliser en dernier recours:
     - le bot sera inactif pendant ce temps.
     - toutes les commandes seront executées à sa reprise.
    """

    await ctx.send(
        "J'ai été arrêté et une console interactive a été ouverte là où je tourne. "
        "Toutes les commandes rateront tant que cette console est ouverte.\n"
        "Soyez rapides, je déteste les opérations à coeur ouvert... :confounded:"
    )

    # Utility function

    local = {
        **globals(),
        **locals(),
        "pprint": pprint,
        "_show": lambda o: print(*dir(o), sep="\n"),
        "__name__": "__console__",
        "__doc__": None,
    }

    code.interact(banner="Ne SURTOUT PAS FAIRE Ctrl+C !\n(TFJM² debugger)", local=local)
    await ctx.send("Tout va mieux !")


@bot.event
async def on_command_error(ctx: Context, error, *args, **kwargs):
    if isinstance(error, commands.CommandInvokeError):
        if isinstance(error.original, UnwantedCommand):
            await ctx.message.delete()
            author: discord.Message
            await ctx.author.send(
                "J'ai supprimé ton message:\n> "
                + ctx.message.clean_content
                + "\nC'est pas grave, c'est juste pour ne pas encombrer "
                "le chat lors du tirage."
            )
            await ctx.author.send("Raison: " + error.original.msg)
            return
        else:
            msg = str(error.original) or str(error)
            traceback.print_tb(error.original.__traceback__, file=sys.stderr)
    else:
        msg = str(error)

    print(repr(error), dir(error), file=sys.stderr)
    await ctx.send(msg)


bot.load_extension("src.cogs.tirages")


if __name__ == "__main__":
    bot.run(TOKEN)
