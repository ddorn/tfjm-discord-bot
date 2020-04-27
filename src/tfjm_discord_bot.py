#!/bin/python
import asyncio
import code
import random
import sys
import traceback
from collections import defaultdict, namedtuple
from pprint import pprint
from typing import Dict, Type

import discord
import yaml
from discord.ext import commands
from discord.ext.commands import Context
from discord.utils import get

from src.cogs.tirages import Tirage, TiragePhase
from src.constants import *
from src.errors import TfjmError, UnwantedCommand


bot = commands.Bot(
    "!", help_command=commands.DefaultHelpCommand(no_category="Commandes")
)

# global variable to hold every running tirage
tirages: Dict[int, Tirage] = {}


@bot.command(
    name="start-draw",
    help="Commence un tirage avec 3 ou 4 équipes.",
    usage="équipe1 équipe2 équipe3 (équipe4)",
)
@commands.has_role(ORGA_ROLE)
async def start_draw(ctx: Context, *teams):
    channel: discord.TextChannel = ctx.channel
    channel_id = channel.id
    if channel_id in tirages:
        raise TfjmError("Il y a déjà un tirage en cours sur cette Channel.")

    if len(teams) not in (3, 4):
        raise TfjmError("Il faut 3 ou 4 équipes pour un tirage.")

    roles = {role.name for role in ctx.guild.roles}
    for team in teams:
        if team not in roles:
            raise TfjmError("Le nom de l'équipe doit être exactement celui du rôle.")

    # Here all data should be valid

    # Prevent everyone from writing except Capitaines, Orga, CNO, Benevole
    read = discord.PermissionOverwrite(send_messages=False)
    send = discord.PermissionOverwrite(send_messages=True)
    r = lambda role_name: get(ctx.guild.roles, name=role_name)
    overwrites = {
        ctx.guild.default_role: read,
        r(CAPTAIN_ROLE): send,
        r(BENEVOLE_ROLE): send,
    }
    await channel.edit(overwrites=overwrites)

    await ctx.send(
        "Nous allons commencer le tirage du premier tour. "
        "Seuls les capitaines de chaque équipe peuvent désormais écrire ici. "
        "Merci de d'envoyer seulement ce que est nécessaire et suffisant au "
        "bon déroulement du tournoi. Vous pouvez à tout moment poser toute question "
        "si quelque chose n'est pas clair ou ne va pas. \n\n"
        "Pour plus de détails sur le déroulement du tirgae au sort, le règlement "
        "est accessible sur https://tfjm.org/reglement."
    )

    tirages[channel_id] = Tirage(ctx, channel_id, teams)
    await tirages[channel_id].phase.start(ctx)


@bot.command(
    name="abort-draw", help="Annule le tirage en cours.",
)
@commands.has_role(ORGA_ROLE)
async def abort_draw_cmd(ctx):
    channel_id = ctx.channel.id
    if channel_id in tirages:
        await tirages[channel_id].end(ctx)
        await ctx.send("Le tirage est annulé.")


@bot.command(name="draw-skip", aliases=["skip"])
@commands.has_role(CNO_ROLE)
async def draw_skip(ctx, *teams):
    channel = ctx.channel.id
    tirages[channel] = tirage = Tirage(ctx, channel, teams)

    tirage.phase = TiragePhase(tirage, round=1)
    for i, team in enumerate(tirage.teams):
        team.tirage_order = [i + 1, i + 1]
        team.passage_order = [i + 1, i + 1]
        team.accepted_problems = [PROBLEMS[i], PROBLEMS[-i - 1]]
    tirage.teams[0].rejected = [{PROBLEMS[3]}, set(PROBLEMS[4:8])]
    tirage.teams[1].rejected = [{PROBLEMS[7]}, set()]

    await ctx.send(f"Skipping to {tirage.phase.__class__.__name__}.")
    await tirage.phase.start(ctx)
    await tirage.update_phase(ctx)


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


@bot.command(name="show")
async def show_cmd(ctx: Context, arg: str):
    if not TIRAGES_FILE.exists():
        await ctx.send("Il n'y a pas encore eu de tirages.")
        return

    with open(TIRAGES_FILE) as f:
        tirages = list(yaml.load_all(f))

    if arg.lower() == "all":
        msg = "\n".join(
            f"{i}: {', '.join(team.name for team in tirage.teams)}"
            for i, tirage in enumerate(tirages)
        )
        await ctx.send(
            "Voici in liste de tous les tirages qui ont été faits. "
            "Vous pouvez en consulter un en particulier avec `!show ID`."
        )
        await ctx.send(msg)
    else:
        try:
            n = int(arg)
            if n < 0:
                raise ValueError
            tirage = tirages[n]
        except (ValueError, IndexError):
            await ctx.send(
                f"`{arg}` n'est pas un identifiant valide. "
                f"Les identifiants valides sont visibles avec `!show all`"
            )
        else:
            await tirage.show(ctx)


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


if __name__ == "__main__":
    bot.run(TOKEN)
