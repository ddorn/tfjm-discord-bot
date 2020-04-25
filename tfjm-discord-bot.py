#!/bin/python
import enum
import os
import sys
import traceback
from collections import defaultdict
from operator import attrgetter
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

with open("problems") as f:
    PROBLEMS = f.read().splitlines()


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

        self.accepted_problem = None
        self.rejected = []
        self.can_refuse = len(PROBLEMS) - 5


class Tirage:
    def __init__(self, ctx, channel, teams):
        assert len(teams) in (3, 4)

        self.channel = channel
        self.teams = [Team(ctx, team) for team in teams]
        self.phase = TirageOrderPhase(self)

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
                await ctx.send(
                    "Le tirage est fini ! Bonne chance à tous pour la suite !"
                )
                del tirages[self.channel]
            else:
                await self.phase.start(ctx)


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

    @teams.setter
    def teams(self, teams):
        self.tirage.teams = teams

    def captain_mention(self, ctx):
        return get(ctx.guild.roles, name=CAPTAIN_ROLE).mention

    async def dice(self, ctx: Context, author, dice):
        await self.fais_pas_chier(ctx)

    async def choose_problem(self, ctx: Context, author, problem):
        await self.fais_pas_chier(ctx)

    async def accept(self, ctx: Context, author, yes):
        await self.fais_pas_chier(ctx)

    def finished(self) -> bool:
        return NotImplemented

    async def start(self, ctx):
        pass

    async def next(self, ctx: Context) -> "Phase":
        return self.NEXT(self.tirage)


class OrderPhase(Phase):
    def __init__(self, tirage, name, order_name, reverse=False):
        super().__init__(tirage)
        self.name = name
        self.reverse = reverse
        self.order_name = order_name

    def order_for(self, team):
        return getattr(team, self.order_name)

    def set_order_for(self, team, order):
        setattr(team, self.order_name, order)

    async def dice(self, ctx, author, dice):
        team = self.team_for(author)

        if self.order_for(team) is None:
            self.set_order_for(team, dice)
            print(f"Team {team.name} has rolled {dice}")
        else:
            await ctx.send(f"{author.mention}: merci de ne lancer qu'un dé.")

    def finished(self) -> bool:
        return all(self.order_for(team) is not None for team in self.teams)

    async def next(self, ctx) -> "Phase":
        orders = [self.order_for(team) for team in self.teams]
        if len(set(orders)) == len(orders):
            # All dice are different: good
            self.teams.sort(key=self.order_for, reverse=self.reverse)
            await ctx.send(
                f"L'ordre {self.name} pour ce tour est donc :\n"
                " - "
                + "\n - ".join(
                    f"{team.role.mention} ({self.order_for(team)})"
                    for team in self.teams
                )
            )
            if self.NEXT is not None:
                return self.NEXT(self.tirage)
            return None
        else:
            # Find dice that are the same
            count = defaultdict(list)
            for team in self.teams:
                count[self.order_for(team)].append(team)

            re_do = []
            for teams in count.values():
                if len(teams) > 1:
                    re_do.extend(teams)

            teams_str = ", ".join(team.role.mention for team in re_do)
            await ctx.send(
                f"Les equipes {teams_str} ont fait le même résultat "
                "et doivent relancer un dé. "
                "Le nouveau lancer effacera l'ancien."
            )
            for team in re_do:
                self.set_order_for(team, None)
            return self


class TiragePhase(Phase):
    """The phase where captains accept or refuse random problems."""

    async def choose_problem(self, ctx: Context, author, problem):
        return await super().choose_problem(ctx, author, problem)

    async def accept(self, ctx: Context, author, yes):
        return await super().accept(ctx, author, yes)

    def finished(self) -> bool:
        return all(team.accepted_problem for team in self.teams)

    async def start(self, ctx: Context):
        # First sort teams according to the tirage_order
        self.teams.sort(key=attrgetter("tirage_order"))

        async with ctx.typing():
            sleep(0.5)
            await ctx.send("Passons au tirage des problèmes !")
            sleep(0.5)
            await ctx.send(
                f"Les {self.captain_mention(ctx)} vont tirer des problèmes au "
                f"hasard, avec `!random-problem` ou `!rp` pour ceux qui aiment "
                f"les abbréviations."
            )
            sleep(0.5)
            await ctx.send(
                "Ils pouront ensuite accepter ou refuser les problèmes avec "
                "`!accept` ou `!refuse`."
            )
            sleep(0.5)
            await ctx.send(
                f"Chaque équipe peut refuser jusqu'a {len(PROBLEMS) - 5} "
                f"problèmes sans pénalité (voir §13 du règlement). "
                f"Un problème déjà rejeté ne compte pas deux fois."
            )
            await ctx.send("C'est parti !")
            sleep(0.5)
            await self.send_instructions(ctx)

    async def send_instructions(self, ctx):
        pass


class PassageOrderPhase(OrderPhase):
    """The phase to determine the chicken's order."""

    NEXT = TiragePhase

    def __init__(self, tirage):
        super().__init__(tirage, "de passage", "passage_order", True)

    async def start(self, ctx):
        await ctx.send(
            "Nous allons maintenant tirer l'ordre de passage durant le tour. "
            "L'ordre du tour sera dans l'ordre décroissant des lancers, "
            "c'est-à-dire que l'équipe qui tire le plus grand nombre "
            "présentera en premier."
        )
        sleep(0.5)

        captain = get(ctx.guild.roles, name=CAPTAIN_ROLE)
        await ctx.send(
            f"Les {captain.mention}s, vous pouvez lancer à nouveau un dé 100 (`!dice 100`)"
        )


class TirageOrderPhase(OrderPhase):
    """Phase to determine the tirage's order."""

    NEXT = PassageOrderPhase

    def __init__(self, tirage):
        super().__init__(tirage, "des tirages", "tirage_order", False)

    async def start(self, ctx):
        captain = get(ctx.guild.roles, name=CAPTAIN_ROLE)

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
    channel = ctx.channel.id
    if channel in tirages:
        raise TfjmError("Il y a déjà un tirage en cours sur cette Channel.")

    if len(teams) not in (3, 4):
        raise TfjmError("Il faut 3 ou 4 équipes pour un tirage.")

    roles = [role.name for role in ctx.guild.roles]
    for team in teams:
        if team not in roles:
            raise TfjmError("Le nom de l'équipe doit être exactement celui du rôle.")

    # Here everything should be alright
    await ctx.send(
        "Nous allons commencer le tirage du premier tour. "
        "Seuls les capitaines de chaque équipe peuvent désormais écrire ici. "
        "Pour plus de détails sur le déroulement du tirgae au sort, le règlement "
        "est accessible sur https://tfjm.org/reglement."
    )

    tirages[channel] = Tirage(ctx, channel, teams)
    await tirages[channel].phase.start(ctx)


@bot.command(name="draw-skip")
async def draw_skip(ctx, *teams):
    channel = ctx.channel.id
    tirages[channel] = tirage = Tirage(ctx, channel, teams)

    tirage.phase = TiragePhase(tirage)
    for i, team in enumerate(tirage.teams):
        team.tirage_order = i
        team.passage_order = i

    await ctx.send(f"Skipping to {tirage.phase.__class__.__name__}.")
    await tirage.phase.start(ctx)


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
