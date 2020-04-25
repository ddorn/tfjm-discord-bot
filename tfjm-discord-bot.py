#!/bin/python

import os
import sys
from typing import List

import discord
from discord.ext import commands
import random

from discord.ext.commands import Context
from discord.utils import get

TOKEN = os.environ.get("TFJM_DISCORD_TOKEN")

if TOKEN is None:
    print("No token for the bot were found.")
    print("You need to set the TFJM_DISCORD_TOKEN variable in your environement")
    print("Or just run:\n")
    print(f'    TFJM_DISCORD_TOKEN="your token here" python tfjm-discord-bot.py')
    print()
    quit(1)

GUILD = "690934836696973404"
ORGA_ROLE = "Orga"
CAPTAIN_ROLE = "Capitaine"


class TfjmError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __repr__(self):
        return self.msg


class Team:
    def __init__(self, name):
        self.name = name


class Tirage:
    def __init__(self, *teams):
        assert len(teams) in (3, 4)

        self.teams = {team: Team(team) for team in teams}


bot = commands.Bot(
    "!", help_command=commands.DefaultHelpCommand(no_category="Commandes")
)

draws = {}


@bot.command(
    name="start-draw",
    help="Commence un tirage avec 3 ou 4 équipes.",
    usage="équipe1 équipe2 équipe3 (équipe4)",
)
@commands.has_role(ORGA_ROLE)
async def start_draw(ctx: Context, *teams):
    guild: discord.Guild = ctx.guild

    channel = ctx.channel.id
    if channel in draws:
        raise TfjmError("Il y a déjà un tirage en cours sur cette Channel.")

    if len(teams) not in (3, 4):
        raise TfjmError("Il faut 3 ou 4 équipes pour un tirage.")

    roles = [role.name for role in ctx.guild.roles]
    for team in teams:
        if team not in roles:
            raise TfjmError("Le nom de l'équipe doit être exactement celui du rôle.")

    captain: discord.Role = get(guild.roles, name=CAPTAIN_ROLE)

    # Here everything should be alright
    await ctx.send(
        "Nous allons commencer le tirage du premier tour. "
        "Seuls les capitaines de chaque équipe peuvent désormais écrire ici. "
        "Pour plus de détails sur le déroulement du tirgae au sort, le règlement "
        "est accessible sur https://tfjm.org/reglement."
    )
    await ctx.send(
        "Nous allons d'abord tirer au sort l'ordre de tirage des problèmes, "
        "puis l'ordre de passage lors du tour."
    )
    await ctx.send(
        f"Les {captain.mention}s, vous pouvez désormais lancer un dé 100 "
        "comme ceci `!dice 100`. "
        "L'ordre des tirages suivants sera l'ordre croissant des lancers. "
    )


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
    if n < 1:
        raise TfjmError(f"Je ne peux pas lancer un dé à {n} faces, désolé.")

    dice = random.randint(1, n)
    await ctx.send(f"Le dé à {n} faces s'est arrêté sur... **{dice}**")


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
    problems = open("problems").readlines()
    problems = [p.strip() for p in problems]
    problem = random.choice(problems)
    await ctx.send(f"Le problème tiré est... **{problem}**")


@bot.event
async def on_command_error(ctx: Context, error, *args, **kwargs):
    if isinstance(error, commands.CommandInvokeError):
        msg = str(error.original)
    else:
        msg = str(error)

    print(repr(error), file=sys.stderr)
    await ctx.send(msg)


if __name__ == "__main__":
    bot.run(TOKEN)
