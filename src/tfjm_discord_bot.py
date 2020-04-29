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

# We allow "! " to catch people that put a space in their commands.
# It must be in first otherwise "!" always match first and the space is not recognised
bot = commands.Bot(("! ", "!"), help_command=TfjmHelpCommand())

# Variable globale qui contient les tirages.
tirages = {}


@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")


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
            msg = (
                error.original.__class__.__name__
                + ": "
                + (str(error.original) or str(error))
            )
            traceback.print_tb(error.original.__traceback__, file=sys.stderr)
    elif isinstance(error, commands.CommandNotFound):
        # Here we just take adventage that the error is formatted this way:
        # 'Command "NAME" is not found'
        name = str(error).partition('"')[2].rpartition('"')[0]
        msg = f"La commande {name} n'éxiste pas. Pour un liste des commandes, envoie `!help`."
    elif isinstance(error, commands.MissingRole):
        msg = f"Il te faut le role de {error.missing_role} pour utiliser cette commande"
    else:
        msg = repr(error)

    print(repr(error), dir(error), file=sys.stderr)
    await ctx.send(msg)


bot.remove_command("help")
bot.load_extension("src.cogs.tirages")
bot.load_extension("src.cogs.teams")
bot.load_extension("src.cogs.dev")
bot.load_extension("src.cogs.misc")


if __name__ == "__main__":
    bot.run(TOKEN)
