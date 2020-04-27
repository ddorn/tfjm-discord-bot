#!/bin/python
import asyncio
import random
from collections import defaultdict, namedtuple
from typing import Type

import discord
import yaml
from discord.ext.commands import Context
from discord.utils import get

from src.constants import *
from src.errors import TfjmError, UnwantedCommand


def in_passage_order(teams, round=0):
    return sorted(teams, key=lambda team: team.passage_order[round] or 0, reverse=True)


class Team(yaml.YAMLObject):
    yaml_tag = "Team"

    def __init__(self, ctx, name):
        self.name = name
        self.mention = get(ctx.guild.roles, name=name).mention
        self.tirage_order = [None, None]
        self.passage_order = [None, None]

        self.accepted_problems = [None, None]
        self.drawn_problem = None  # Waiting to be accepted or refused
        self.rejected = [set(), set()]

    def coeff(self, round):
        if len(self.rejected[round]) <= MAX_REFUSE:
            return 2
        else:
            return 2 - 0.5 * (len(self.rejected[round]) - MAX_REFUSE)

    def details(self, round):
        return f"""{self.mention}:
 - Accepté: {self.accepted_problems[round]}
 - Refusés: {", ".join(p[0] for p in self.rejected[round]) if self.rejected[round] else "aucun"}
 - Coefficient: {self.coeff(round)}
 - Ordre au tirage: {self.tirage_order[round]}
 - Ordre de passage: {self.passage_order[round]}
"""


class Tirage(yaml.YAMLObject):
    yaml_tag = "Tirage"

    def __init__(self, ctx, channel, teams):
        assert len(teams) in (3, 4)

        self.channel: int = channel
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

    async def dice(self, ctx, n) -> bool:
        if n != 100:
            raise UnwantedCommand(
                "C'est un dé à 100 faces qu'il faut tirer! (`!dice 100`)"
            )

        await self.phase.dice(ctx, ctx.author, random.randint(1, n))
        await self.update_phase(ctx)

    async def choose_problem(self, ctx):
        await self.phase.choose_problem(ctx, ctx.author, random.choice(PROBLEMS))
        await self.update_phase(ctx)

    async def accept(self, ctx, yes):
        await self.phase.accept(ctx, ctx.author, yes)
        await self.update_phase(ctx)

    async def update_phase(self, ctx):
        if self.phase.finished():
            next_class = await self.phase.next(ctx)

            if next_class is None:
                self.phase = None
                await ctx.send(
                    "Le tirage est fini ! Bonne chance à tous pour la suite !"
                )
                await self.show(ctx)
                await self.end(ctx)
            else:
                # Continue on the same round.
                # If a Phase wants to change the round
                # it needs to change its own round.
                self.phase = next_class(self, self.phase.round)
                await self.phase.start(ctx)

    async def end(self, ctx):

        from src.tfjm_discord_bot import tirages

        del tirages[self.channel]

        # Allow everyone to send messages again
        send = discord.PermissionOverwrite()  # reset
        await ctx.channel.edit(overwrites={ctx.guild.default_role: send})

        tl = []
        if TIRAGES_FILE.exists():
            with open(TIRAGES_FILE) as f:
                tl = list(yaml.load_all(f))
        else:
            TIRAGES_FILE.touch()
        tl.append(self)
        with open(TIRAGES_FILE, "w") as f:
            yaml.dump_all(tl, f)

        await ctx.send(
            f"A tout moment, ce rapport peut être envoyé avec `!show {len(tl) - 1}`"
        )

    async def show(self, ctx):
        teams = ", ".join(team.mention for team in self.teams)
        msg = f"Voici un résumé du tirage entre les équipes {teams}."

        if len(self.teams) == 3:
            table = """```
    +-----+---------+---------+---------+
    |     | Phase 1 | Phase 2 | Phase 3 |
    |     |   Pb {0.pb}  |   Pb {1.pb}  |   Pb {2.pb}  |
    +-----+---------+---------+---------+
    | {0.name} |   Déf   |   Rap   |   Opp   |
    +-----+---------+---------+---------+
    | {1.name} |   Opp   |   Déf   |   Rap   |
    +-----+---------+---------+---------+
    | {2.name} |   Rap   |   Opp   |   Déf   |
    +-----+---------+---------+---------+
```"""
        else:
            table = """```
    +-----+---------+---------+---------+---------+
    |     | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
    |     |   Pb {0.pb}  |   Pb {1.pb}  |   Pb {2.pb}  |   Pb {3.pb}  |
    +-----+---------+---------+---------+---------+
    | {0.name} |   Déf   |         |   Rap   |   Opp   |
    +-----+---------+---------+---------+---------+
    | {0.name} |   Opp   |   Déf   |         |   Rap   |
    +-----+---------+---------+---------+---------+
    | {0.name} |   Rap   |   Opp   |   Déf   |         |
    +-----+---------+---------+---------+---------+
    | {0.name} |         |   Rap   |   Opp   |   Déf   |
    +-----+---------+---------+---------+---------+
```"""
        Record = namedtuple("Record", ["name", "pb", "penalite"])

        for round in (0, 1):
            records = [
                Record(
                    team.name,
                    (team.accepted_problems[round] or "- None")[0],
                    f"k = {team.coeff(round)} ",
                )
                for team in in_passage_order(self.teams, round)
            ]

            msg += f"\n\n**{ROUND_NAMES[round].capitalize()}**:\n"
            msg += table.format(*records) + "\n"
            for team in self.teams:
                msg += team.details(round)

        await ctx.send(msg)


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
        raise UnwantedCommand()

    async def choose_problem(self, ctx: Context, author, problem):
        raise UnwantedCommand()

    async def accept(self, ctx: Context, author, yes):
        raise UnwantedCommand()

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
            await ctx.send(f"L'équipe {team.mention} a obtenu... **{dice}**")
        else:
            raise UnwantedCommand("tu as déjà lancé un dé !")

    def finished(self) -> bool:
        return all(self.order_for(team) is not None for team in self.teams)

    async def next(self, ctx) -> "Type[Phase]":
        orders = [self.order_for(team) for team in self.teams]
        if len(set(orders)) == len(orders):
            # All dice are different: good
            self.teams.sort(key=self.order_for, reverse=self.reverse)
            await ctx.send(
                f"L'ordre {self.name} pour ce tour est donc :\n"
                " - "
                + "\n - ".join(
                    f"{team.mention} ({self.order_for(team)})" for team in self.teams
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


class TiragePhase(Phase):
    """The phase where captains accept or refuse random problems."""

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
            raise UnwantedCommand(
                f"C'est à {team.mention} de choisir "
                f"un problème, merci d'attendre :)"
            )

        assert (
            team.accepted_problems[self.round] is None
        ), "Choosing pb for a team that has a pb..."

        if team.drawn_problem:
            raise UnwantedCommand(
                "Vous avez déjà tiré un problème, merci de l'accepter (`!yes`) "
                "ou de le refuser (`!no)`."
            )

        await ctx.send(f"{team.mention} a tiré **{problem}** !")
        if not self.available(problem):
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
            raise UnwantedCommand(
                f"c'est à {team.mention} "
                f"de choisir un problème, merci d'attendre :)"
            )

        assert (
            team.accepted_problems[self.round] is None
        ), "Choosing pb for a team that has a pb..."

        if not team.drawn_problem:
            if yes:
                raise UnwantedCommand(
                    "Tu es bien optimiste pour vouloir accepter un problème "
                    "avant de l'avoir tiré !"
                )
            else:
                raise UnwantedCommand(
                    "Halte là ! Ce serait bien de tirer un problème d'abord... "
                    "et peut-être qu'il te plaira :) "
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
                msg = f"{team.mention} a refusé **{team.drawn_problem}** "
                if team.drawn_problem in team.rejected[self.round]:
                    msg += "sans pénalité."
                else:
                    msg += "!"
                    team.rejected[self.round].add(team.drawn_problem)
                await ctx.send(msg)

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
            await asyncio.sleep(0.5)
            await ctx.send("Passons au tirage des problèmes !")
            await asyncio.sleep(0.5)
            await ctx.send(
                f"Les {self.captain_mention(ctx)}s vont tirer des problèmes au "
                f"hasard, avec `!random-problem` ou `!rp` pour ceux qui aiment "
                f"les abbréviations."
            )
            await asyncio.sleep(0.5)
            await ctx.send(
                "Ils pouront ensuite accepter ou refuser les problèmes avec "
                "`!accept` ou `!refuse`."
            )
            await asyncio.sleep(0.5)
            await ctx.send(
                f"Chaque équipe peut refuser jusqu'a {MAX_REFUSE} "
                f"problèmes sans pénalité (voir §13 du règlement). "
                f"Un problème déjà rejeté ne compte pas deux fois."
            )
            await ctx.send("Bonne chance à tous ! C'est parti...")

        else:
            # Second round
            await asyncio.sleep(0.5)
            await ctx.send(
                "Il reste juste le tirage du deuxième tour. Les règles sont les mêmes qu'avant "
                "à la seule différence qu'une équipe ne peut pas tirer le problème "
                "sur lequel elle est passée au premier tour."
            )

        await asyncio.sleep(1.5)
        await ctx.send(
            f"{self.current_team.mention} à toi l'honneur! "
            f"Lance `!random-problem` quand tu veux."
        )

    async def next(self, ctx: Context) -> "Type[Phase]":
        if self.round == 0:
            await ctx.send("Nous allons passer au deuxième tour")
            self.round = 1
            return TirageOrderPhase
        return None


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
        await asyncio.sleep(0.5)

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

        await asyncio.sleep(
            0.5
        )  # The bot is more human if it doesn't type at the speed of light
        await ctx.send(
            "Nous allons d'abord tirer au sort l'ordre de tirage des problèmes "
            f"pour le {ROUND_NAMES[self.round]}, "
            "puis l'ordre de passage lors de ce tour."
        )
        await asyncio.sleep(0.5)
        await ctx.send(
            f"Les {captain.mention}s, vous pouvez désormais lancer un dé 100 "
            "comme ceci `!dice 100`. "
            "L'ordre des tirages suivants sera l'ordre croissant des lancers. "
        )
