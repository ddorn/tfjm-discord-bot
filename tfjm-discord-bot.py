#!/bin/python
import os
import random
import sys
import traceback
from collections import defaultdict
from operator import attrgetter
from time import sleep
from typing import Dict, Type

import discord
from discord.ext import commands
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
MAX_REFUSE = len(PROBLEMS) - 5

ROUND_NAMES = ["premier tour", "deuxième tour"]


class TfjmError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __repr__(self):
        return self.msg


class Team:
    def __init__(self, ctx, name):
        self.name = name
        self.role = get(ctx.guild.roles, name=name)
        self.tirage_order = [None, None]
        self.passage_order = [None, None]

        self.accepted_problems = [None, None]
        self.drawn_problem = None  # Waiting to be accepted or refused
        self.rejected = [set(), set()]

    @property
    def mention(self):
        return self.role.mention


class Tirage:
    def __init__(self, ctx, channel, teams):
        assert len(teams) in (3, 4)

        self.channel = channel
        self.teams = [Team(ctx, team) for team in teams]
        self.phase = TirageOrderPhase(self, round=0)

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

    async def choose_problem(self, ctx, author, problem):
        await self.phase.choose_problem(ctx, author, problem)
        await self.update_phase(ctx)

    async def accept(self, ctx, author, yes):
        await self.phase.accept(ctx, author, yes)
        await self.update_phase(ctx)

    async def update_phase(self, ctx):
        if self.phase.finished():
            next_class = await self.phase.next(ctx)

            if next_class is None:
                await ctx.send(
                    "Le tirage est fini ! Bonne chance à tous pour la suite !"
                )
                del tirages[self.channel]
            else:
                # Continue on the same round.
                # If a Phase wants to change the round
                # it needs to change its own round.
                self.phase = next_class(self, self.phase.round)
                await self.phase.start(ctx)


class Phase:
    NEXT = None

    def __init__(self, tirage, round=0):
        """
        A Phase of the tirage.

        :param tirage: Backreference to the tirage
        :param round: round number, 0 for the first round and 1 for the second
        """

        assert round in (0, 1)
        self.round = round
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

    async def next(self, ctx: Context) -> "Type[Phase]":
        return self.NEXT


class OrderPhase(Phase):
    def __init__(self, tirage, round, name, order_name, reverse=False):
        super().__init__(tirage, round)
        self.name = name
        self.reverse = reverse
        self.order_name = order_name

    def order_for(self, team):
        return getattr(team, self.order_name)[self.round]

    def set_order_for(self, team, order):
        getattr(team, self.order_name)[self.round] = order

    async def dice(self, ctx, author, dice):
        team = self.team_for(author)

        if self.order_for(team) is None:
            self.set_order_for(team, dice)
            print(f"Team {team.name} has rolled {dice}")
        else:
            await ctx.send(f"{author.mention}: merci de ne lancer qu'un dé.")

    def finished(self) -> bool:
        return all(self.order_for(team) is not None for team in self.teams)

    async def next(self, ctx) -> "Type[Phase]":
        orders = [self.order_for(team) for team in self.teams]
        if len(set(orders)) == len(orders):
            # All dice are different: good
            self.teams.sort(key=self.order_for, reverse=self.reverse)
            await ctx.send(
                f"L'ordre {self.name} pour ce 9 est donc :\n"
                " - "
                + "\n - ".join(
                    f"{team.role.mention} ({self.order_for(team)})"
                    for team in self.teams
                )
            )
            return self.NEXT
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
            # We need to do this phase again.
            return self.__class__


class ShowPhase(Phase):
    """Phase where the bot resumes all that happened."""

    NEXT = None


class TiragePhase(Phase):
    """The phase where captains accept or refuse random problems."""

    NEXT = ShowPhase

    def __init__(self, tirage, round=0):
        """
        The main phase of the Tirage.
        :param tirage: Backreference to the tirage
        :param round: round number, 0 for the first round and 1 for the second
        """

        super().__init__(tirage, round)
        self.turn = 0

    @property
    def current_team(self):
        return self.teams[self.turn]

    def available(self, problem):
        return all(team.accepted_problems[self.round] != problem for team in self.teams)

    async def choose_problem(self, ctx: Context, author, problem):
        team = self.current_team
        if self.team_for(author) != team:
            await ctx.send(
                f"{author.mention}: c'est à {team.mention} "
                f"de choisir un problème, merci d'attendre :)"
            )
            return

        assert (
            team.accepted_problems[self.round] is None
        ), "Choosing pb for a team that has a pb..."

        if team.drawn_problem:
            await ctx.send(
                "Vous avez déjà tiré un problème, merci de l'accepter (`!yes`) "
                "ou de le refuser (`!no)`."
            )
        elif not self.available(problem):
            await ctx.send(
                f"Malheureusement, **{problem}** à déjà été choisi, "
                f"vous pouvez tirer un nouveau problème."
            )
        elif problem in team.accepted_problems:
            await ctx.send(
                f"{team.mention} à tiré **{problem}** mais "
                f"l'a déjà présenté au premier tour. "
                f"Vous pouvez directement piocher un autre problème (`!rp`)."
            )
        elif problem in team.rejected[self.round]:
            team.drawn_problem = problem
            await ctx.send(
                f"Vous avez déjà refusé **{problem}**, "
                f"vous pouvez le refuser à nouveau (`!refuse`) et "
                f"tirer immédiatement un nouveau problème "
                f"ou changer d'avis et l'accepter (`!accept`)."
            )
        else:
            team.drawn_problem = problem
            if len(team.rejected[self.round]) >= MAX_REFUSE:
                await ctx.send(
                    f"Vous pouvez accepter ou refuser **{problem}** "
                    f"mais si vous choisissez de le refuser, il y "
                    f"aura une pénalité de 0.5 sur le multiplicateur du "
                    f"défenseur."
                )
            else:
                await ctx.send(
                    f"Vous pouvez accepter (`!oui`) ou refuser (`!non`) **{problem}**. "
                    f"Il reste {MAX_REFUSE - len(team.rejected[self.round])} refus sans pénalité "
                    f"pour {team.mention}."
                )

    async def accept(self, ctx: Context, author, yes):
        team = self.current_team

        if self.team_for(author) != team:
            await ctx.send(
                f"{author.mention}: c'est à {team.mention} "
                f"de choisir un problème, merci d'attendre :)"
            )
            return

        assert (
            team.accepted_problems[self.round] is None
        ), "Choosing pb for a team that has a pb..."

        if not team.drawn_problem:
            if yes:
                await ctx.send(
                    "Vous êtes bien optimistes pour vouloir accepter un problème "
                    "avant de l'avoir tiré !"
                )
            else:
                await ctx.send(
                    "Halte là ! Ce serait bien de tirer un problème d'abord... "
                    "et peut-être qu'il vous plaira :) "
                )
        else:
            if yes:
                team.accepted_problems[self.round] = team.drawn_problem
                await ctx.send(
                    f"L'équipe {team.mention} a accepté "
                    f"**{team.accepted_problems[self.round]}** ! Les autres équipes "
                    f"ne peuvent plus l'accepter."
                )
            else:
                if team.drawn_problem in team.rejected[self.round]:
                    await ctx.send(
                        f"{team.mention} a refusé **{team.drawn_problem}** "
                        f"sans pénalité."
                    )
                else:
                    team.rejected[self.round].add(team.drawn_problem)
                    await ctx.send(f"{team.mention} a refusé **{team.drawn_problem}**!")

            team.drawn_problem = None

            # Next turn
            if self.finished():
                self.turn = None
                return

            # Find next team that needs to draw.
            i = (self.turn + 1) % len(self.teams)
            while self.teams[i].accepted_problems[self.round]:
                i = (i + 1) % len(self.teams)
            self.turn = i

            await ctx.send(
                f"C'est au tour de {self.current_team.mention} de choisir un problème."
            )

    def finished(self) -> bool:
        return all(team.accepted_problems[self.round] for team in self.teams)

    async def start(self, ctx: Context):
        # First sort teams according to the tirage_order
        self.teams.sort(key=lambda team: team.tirage_order[self.round])

        if self.round == 0:
            sleep(0.5)
            await ctx.send("Passons au tirage des problèmes !")
            sleep(0.5)
            await ctx.send(
                f"Les {self.captain_mention(ctx)}s vont tirer des problèmes au "
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
                f"Chaque équipe peut refuser jusqu'a {MAX_REFUSE} "
                f"problèmes sans pénalité (voir §13 du règlement). "
                f"Un problème déjà rejeté ne compte pas deux fois."
            )
            await ctx.send("Bonne chance à tous ! C'est parti...")

        else:
            # Second round
            sleep(0.5)
            await ctx.send(
                "Il reste juste le tirage du deuxième tour. Les règles sont les mêmes qu'avant "
                "à la seule différence qu'une équipe ne peut pas tirer le problème "
                "sur lequel elle est passée au premier tour."
            )

        sleep(1.5)
        await ctx.send(
            f"{self.current_team.mention} à toi l'honneur! "
            f"Lance `!random-problem` quand tu veux."
        )

    async def next(self, ctx: Context) -> "Type[Phase]":
        if self.round == 0:
            await ctx.send("Nous allons passer au deuxième tour")
            self.round = 1
            return TirageOrderPhase
        return ShowPhase


class PassageOrderPhase(OrderPhase):
    """The phase to determine the chicken's order."""

    NEXT = TiragePhase

    def __init__(self, tirage, round=0):
        super().__init__(tirage, round, "de passage", "passage_order", True)

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

    def __init__(self, tirage, round=0):
        super().__init__(tirage, round, "des tirages", "tirage_order", False)

    async def start(self, ctx):
        captain = get(ctx.guild.roles, name=CAPTAIN_ROLE)

        sleep(0.5)  # The bot is more human if it doesn't type at the speed of light
        await ctx.send(
            "Nous allons d'abord tirer au sort l'ordre de tirage des problèmes "
            f"pour le {ROUND_NAMES[self.round]}, "
            "puis l'ordre de passage lors de ce tour."
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
        team.tirage_order = [i, None]
        team.passage_order = [i, None]

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

    channel = ctx.channel.id
    if channel in tirages:
        # If it is a captain
        author: discord.Member = ctx.author
        if get(author.roles, name=CAPTAIN_ROLE) is not None:
            await tirages[channel].choose_problem(ctx, ctx.author, problem)


@bot.command(
    name="accept",
    help="Accepte le problème qui vient d'être tiré. \n Ne fonctionne que lors d'un tirage.",
    aliases=["oui", "yes", "o", "accepte", "ouiiiiiii"],
)
async def accept_cmd(ctx):
    channel = ctx.channel.id
    if channel in tirages:
        # If it is a captain
        author: discord.Member = ctx.author
        if get(author.roles, name=CAPTAIN_ROLE) is not None:
            await tirages[channel].accept(ctx, ctx.author, True)


@bot.command(
    name="refuse",
    help="Refuse le problème qui vient d'être tiré. \n Ne fonctionne que lors d'un tirage.",
    aliases=["non", "no", "n"],
)
async def refuse_cmd(ctx):
    channel = ctx.channel.id
    if channel in tirages:
        # If it is a captain
        author: discord.Member = ctx.author
        if get(author.roles, name=CAPTAIN_ROLE) is not None:
            await tirages[channel].accept(ctx, ctx.author, False)


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
