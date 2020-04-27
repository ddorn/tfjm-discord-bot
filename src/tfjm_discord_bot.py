#!/bin/python
import code
import random
import sys
import traceback
from pprint import pprint

import discord
from discord.ext import commands
from discord.ext.commands import Context

from src.constants import *
from src.errors import TfjmError, UnwantedCommand

bot = commands.Bot("!", help_command=commands.MinimalHelpCommand(no_category="Autres"))

# Variable globale qui contient les tirages.
tirages = {}


@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")


@bot.command(
    name="dice",
    help="Lance un dé à `n` faces. ",
    aliases=["de", "dé", "roll"],
    usage="n",
)
async def dice(ctx: Context, n: int):
    channel = ctx.channel.id
    if channel in tirages:
        await tirages[channel].dice(ctx, n)
    else:
        if n < 1:
            raise TfjmError(f"Je ne peux pas lancer un dé à {n} faces, désolé.")

        dice = random.randint(1, n)
        await ctx.send(f"Le dé à {n} face{'s'*(n>1)} s'est arrêté sur... **{dice}**")


@bot.command(
    name="choose",
    help="Choisit une option parmi tous les arguments.",
    usage="choix1 choix2...",
    aliases=["choice", "choix", "ch"],
)
async def choose(ctx: Context, *args):
    choice = random.choice(args)
    await ctx.send(f"J'ai choisi... **{choice}**")


@bot.command(
    name="random-problem",
    help="Choisit un problème parmi ceux de cette année.",
    aliases=["rp", "problème-aléatoire", "probleme-aleatoire", "pa"],
)
async def random_problem(ctx: Context):
    channel = ctx.channel.id
    if channel in tirages:
        await tirages[channel].choose_problem(ctx)
    else:
        problem = random.choice(PROBLEMS)
        await ctx.send(f"Le problème tiré est... **{problem}**")


@bot.command(
    name="accept",
    help="Accepte le problème qui vient d'être tiré. \n Ne fonctionne que lors d'un tirage.",
    aliases=["oui", "yes", "o", "accepte", "ouiiiiiii"],
)
async def accept_cmd(ctx):
    channel = ctx.channel.id
    if channel in tirages:
        await tirages[channel].accept(ctx, True)
    else:
        await ctx.send(f"{ctx.author.mention} approuve avec vigeur !")


@bot.command(
    name="refuse",
    help="Refuse le problème qui vient d'être tiré. \n Ne fonctionne que lors d'un tirage.",
    aliases=["non", "no", "n", "nope", "jaaamais"],
)
async def refuse_cmd(ctx):
    channel = ctx.channel.id
    if channel in tirages:
        await tirages[channel].accept(ctx, False)
    else:
        await ctx.send(f"{ctx.author.mention} nie tout en block !")


@bot.command(name="interrupt")
@commands.has_role(CNO_ROLE)
async def interrupt_cmd(ctx):
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
