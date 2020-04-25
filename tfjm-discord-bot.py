#!/bin/python
import enum
import os
import sys
import traceback
from collections import defaultdict
from time import sleep
from typing import List, Dict

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

TIRAGE_ORDER = 0
PASSAGE_ORDER = 1


class TfjmError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __repr__(self):
        return self.msg


class Team:
    def __init__(self, ctx, name):
        self.name = name
        self.role = get(ctx.guild.roles, name=name)
        self.tirage_order = None
        self.passage_order = None


class Tirage:
    def __init__(self, ctx, channel, teams):
        assert len(teams) in (3, 4)

        self.channel = channel
        self.teams = [Team(ctx, team) for team in teams]
        self.phase = OrderPhase(self)

    def team_for(self, author):
        for team in self.teams:
            if get(author.roles, name=team.name):
                return team

        # Should theoretically not happen
        raise TfjmError(
            "Tu n'es pas dans une des équipes qui font le tirage, "
            "merci de ne pas intervenir."
        )

    async def dice(self, ctx, author, dice):
        await self.phase.dice(ctx, author, dice)
        await self.update_phase(ctx)

    async def update_phase(self, ctx):
        if self.phase.finished():
            self.phase = await self.phase.next(ctx)
        if self.phase is None:
            await ctx.send("Le tirage est fini ! Bonne chance à tous pour la suite !")
            del tirages[self.channel]


class Phase:
    NEXT = None

    def __init__(self, tirage):
        self.tirage: Tirage = tirage

    async def fais_pas_chier(self, ctx):
        await ctx.send(
            "Merci d'envoyer seulement les commandes nécessaires et suffisantes."
        )

    def team_for(self, author):
        return self.tirage.team_for(author)

    @property
    def teams(self):
        return self.tirage.teams

    async def dice(self, ctx: Context, author, dice):
        await self.fais_pas_chier(ctx)

    async def choose_problem(self, ctx: Context, author, problem):
        await self.fais_pas_chier(ctx)

    async def accept(self, ctx: Context, author, yes):
        await self.fais_pas_chier(ctx)

    def finished(self) -> bool:
        return NotImplemented

    async def next(self, ctx: Context) -> "Phase":
        return self.NEXT(self.tirage)


class OrderPhase(Phase):
    async def dice(self, ctx, author, dice):
        team = self.team_for(author)

        if team.tirage_order is None:
            team.tirage_order = dice
            print(f"Team {team.name} has rolled {dice}")
        else:
            await ctx.send(f"{author.mention}: merci de ne lancer qu'un dé.")

    def finished(self) -> bool:
        return all(team.tirage_order is not None for team in self.teams)

    async def next(self, ctx) -> "Phase":
        orders = [team.tirage_order for team in self.teams]
        if len(set(orders)) == len(orders):
            # All dice are different: good
            return self.NEXT
        else:
            # Find dice that are the same
            count = defaultdict(list)
            for team in self.teams:
                count[team.tirage_order].append(team)

            re_do = []
            for dice, teams in count.items():
                if len(teams) > 1:
                    re_do.extend(teams)

            teams_str = ", ".join(team.role.mention for team in re_do)
            await ctx.send(
                f"Les equipes {teams_str} ont fait le même résultat "
                "et doivent relancer un dé. "
                "Le nouveau lancer effacera l'ancien."
            )
            for team in re_do:
                team.tirage_order = None
            return self


bot = commands.Bot(
    "!", help_command=commands.DefaultHelpCommand(no_category="Commandes")
)

tirages: Dict[int, Tirage] = {}


@bot.command(
    name="start-draw",
    help="Commence un tirage avec 3 ou 4 équipes.",
    usage="équipe1 équipe2 équipe3 (équipe4)",
)
@commands.has_role(ORGA_ROLE)
async def start_draw(ctx: Context, *teams):
    guild: discord.Guild = ctx.guild

    channel = ctx.channel.id
    if channel in tirages:
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
    sleep(0.5)  # The bot is more human if it doesn't type at the speed of light
    await ctx.send(
        "Nous allons d'abord tirer au sort l'ordre de tirage des problèmes, "
        "puis l'ordre de passage lors du tour."
    )
    sleep(0.5)
    await ctx.send(
        f"Les {captain.mention}s, vous pouvez désormais lancer un dé 100 "
        "comme ceci `!dice 100`. "
        "L'ordre des tirages suivants sera l'ordre croissant des lancers. "
    )

    tirages[channel] = Tirage(ctx, channel, teams)


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

    # Here we seed the result to Tirage if needed
    channel = ctx.channel.id
    if n == 100 and channel in tirages:
        # If it is a captain
        author: discord.Member = ctx.author
        if get(author.roles, name=CAPTAIN_ROLE) is not None:
            await tirages[channel].dice(ctx, author, dice)


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
        msg = str(error.original) or str(error)
        traceback.print_tb(error.original.__traceback__, file=sys.stderr)
    else:
        msg = str(error)

    print(repr(error), dir(error), file=sys.stderr)
    await ctx.send(msg)


if __name__ == "__main__":
    bot.run(TOKEN)
