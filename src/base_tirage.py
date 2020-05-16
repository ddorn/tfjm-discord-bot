import asyncio
import random
import sys
import traceback
from functools import wraps
from pathlib import Path
from pprint import pprint

from io import StringIO
from typing import Type, Union, Dict, List

import discord
import yaml

from src.constants import *


class Event(asyncio.Event):
    def __init__(self, team: str, value: Union[bool, int, str]):
        super(Event, self).__init__()
        self.value = value
        self.team = team
        self.response = None


class Team:
    yaml_tag = "Team"

    def __init__(self, team_role):
        self.name = team_role.name
        self.mention = team_role.mention

        self.accepted_problems = [None, None]
        self.rejected = [set(), set()]

    def __str__(self):
        s = StringIO()
        pprint(self.__dict__, stream=s)
        s.seek(0)
        return s.read()

    __repr__ = __str__

    def coeff(self, round):
        if len(self.rejected[round]) <= MAX_REFUSE:
            return 2
        else:
            return 2 - 0.5 * (len(self.rejected[round]) - MAX_REFUSE)

    def details(self, round):

        info = {
            # "Accepté": self.accepted_problems[round],
            "Refusés": ", ".join(p[0] for p in self.rejected[round])
            if self.rejected[round]
            else "aucun",
            "Coefficient": self.coeff(round),
            # "Ordre passage": self.passage_order[round],
        }

        width = max(map(len, info))

        return "\n".join(f"`{n.rjust(width)}`: {v}" for n, v in info.items())


#
#         return f""" - Accepté: {self.accepted_problems[round]}
#  - Refusés: {", ".join(p[0] for p in self.rejected[round]) if self.rejected[round] else "aucun"}
#  - Coefficient: {self.coeff(round)}
#  - Ordre au tirage: {self.tirage_order[round]}
#  - Ordre de passage: {self.passage_order[round]}
# """


class Poule(yaml.YAMLObject):
    yaml_tag = "Poule"

    def __init__(self, poule, rnd):
        self.poule = poule
        self.rnd = rnd

    def __str__(self):
        return f"{self.poule}{self.rnd + 1}"


class BaseTirage(yaml.YAMLObject):
    yaml_tag = "Tirage"

    def __init__(self, *teams: discord.Role, fmt=(3, 3)):
        assert sum(fmt) == len(teams), "Different number of teams and format"

        self.teams: Dict[str, Team] = {t.name: Team(t) for t in teams}
        self.format = fmt
        self.queue = asyncio.Queue()
        self.poules: Dict[Poule, List[str]] = {}
        """A mapping between the poule and the list of teams in this poule."""

    def availaible(self, pb, poule):
        pbs = [
            self.teams[team].accepted_problems[poule.rnd] for team in self.poules[poule]
        ]

        if len(self.poules[poule]) < 5:
            return pb not in pbs
        else:
            return pbs.count(pb) < 2

    async def event(self, event: Event):
        event.set()
        await self.queue.put(event)
        await event.wait()
        return event.response

    async def dice(self, trigram):
        return await self.event(Event(trigram, random.randint(1, 100)))

    async def rproblem(self, trigram):
        team = self.teams[trigram]
        rnd = 0 if team.accepted_problems[0] is None else 1
        for poule, teams in self.poules.items():
            if trigram in teams and poule.rnd == rnd:
                break
        else:
            return await self.warn_wrong_team(None, trigram)

        available = [
            pb
            for pb in PROBLEMS
            if pb not in team.accepted_problems and self.availaible(pb, poule)
        ]
        return await self.event(Event(trigram, random.choice(available)))

    async def accept(self, trigram, yes: bool):
        return await self.event(Event(trigram, yes))

    async def next(self, typ, team=None):
        while True:
            event = await self.queue.get()
            if team is not None and event.team != team:
                await self.warn_wrong_team(team, event.team)
            elif not isinstance(event.value, typ):
                await self.warn_unwanted(typ, event.value)
            else:
                event.clear()
                return event
            event.clear()

    async def run(self):

        await self.info_start()

        self.poules = await self.make_poules()

        for poule in self.poules:
            await self.draw_poule(poule)

        await self.info_finish()

    async def get_dices(self, teams):
        dices = {t: None for t in teams}
        collisions = list(teams)
        while collisions:

            for t in collisions:
                dices[t] = None

            while None in dices.values():
                event = await self.next(int)

                if event.team not in dices:
                    await self.warn_wrong_team(None, event.team)
                elif dices[event.team] is None:
                    dices[event.team] = event.value
                    await self.info_dice(event.team, event.value)
                else:
                    await self.warn_twice(int)

            collisions = [t for t in teams if list(dices.values()).count(dices[t]) > 1]
            if collisions:
                await self.warn_colisions(collisions)

        return dices

    async def make_poules(self):
        poules = {}
        for rnd in (0, 1):
            await self.start_make_poule(rnd)

            dices = await self.get_dices(self.teams)
            sorted_teams = sorted(self.teams, key=lambda t: dices[t])

            idx = 0
            for i, qte in enumerate(self.format):
                letter = chr(ord("A") + i)
                poules[Poule(letter, rnd)] = sorted_teams[idx : idx + qte]
                idx += qte

        await self.annonce_poules(poules)
        return poules

    async def draw_poule(self, poule):

        await self.start_draw_poule(poule)

        # Trigrams in draw order
        trigrams = await self.draw_order(poule)

        # Teams in draw order
        teams = [self.teams[tri] for tri in trigrams]
        current = 0
        while not all(team.accepted_problems[poule.rnd] for team in teams):
            team = teams[current]
            if team.accepted_problems[poule.rnd] is not None:
                # The team already accepted a problem
                current += 1
                current %= len(teams)
                continue

            # Choose problem
            await self.start_select_pb(team)
            pevent = await self.next(str, team.name)
            # TODO: Add check for already selected / taken by someone else
            # This is not a bug for now, since it cannot happen yet
            await self.info_draw_pb(team, pevent.value, poule.rnd)

            # Accept it
            accept = await self.next(bool, team.name)
            if accept.value:
                team.accepted_problems[poule.rnd] = pevent.value
                await self.info_accepted(
                    team, pevent.value, self.availaible(pevent.value, poule)
                )
            else:
                await self.info_rejected(team, pevent.value, rnd=poule.rnd)
                team.rejected[poule.rnd].add(pevent.value)

            current += 1
            current %= len(teams)

        if len(teams) == 5:
            # We can determine the passage order only once problems are drawn.
            order = [self.teams[tri] for tri in self.poules[poule]]
            pbs = [team.accepted_problems[poule.rnd] for team in order]

            doubles = []
            i = 0
            while i < len(order):
                team = order[i]
                if pbs.count(team.accepted_problems[poule.rnd]) == 2:
                    # We pop the two with the same pb and add them to the doubles
                    doubles.append(order.pop(i))
                    other = next(
                        filter(
                            lambda t: team.accepted_problems[poule.rnd]
                            == t.accepted_problems[poule.rnd],
                            order,
                        )
                    )
                    doubles.append(other)
                    order.remove(other)
                else:
                    i += 1
            # The conflicts
            order = doubles + order
            self.poules[poule] = order

        await self.annonce_poule(poule)

    async def draw_order(self, poule):
        await self.start_draw_order(poule)

        teams = self.poules[poule]
        dices = await self.get_dices(teams)

        order = sorted(teams, key=lambda t: dices[t], reverse=True)

        await self.annonce_draw_order(order)
        return order

    async def warn_unwanted(self, wanted: Type, got: Type):
        """Called when a event of an unwanted type occurs."""

    async def warn_wrong_team(self, expected, got):
        """Called when a team that should not play now put an event"""

    async def warn_colisions(self, collisions: List[str]):
        """Called when there are collisions in a dice tirage."""

    async def warn_twice(self, typ: Type):
        """Called when an event appears once again and not wanted."""

    async def start_make_poule(self, rnd):
        """Called when it starts drawing the poules for round `rnd`"""

    async def start_draw_poule(self, poule):
        """Called when we start a poule."""

    async def start_draw_order(self, poule):
        """Called when we start to draw the order."""

    async def start_select_pb(self, team):
        """Called when a team needs to select a problem."""

    async def annonce_poules(self, poules):
        """Called when all poules are defined."""

    async def annonce_draw_order(self, order):
        """Called when the drawing order is defined."""

    async def annonce_poule(self, poule):
        """Called when the problems and order for a poule is known."""

    async def info_start(self):
        """Called at the start of the tirage."""

    async def info_finish(self):
        """Called when the tirage has ended."""

    async def info_dice(self, team, dice):
        """Called on a dice roll."""

    async def info_draw_pb(self, team, pb, rnd):
        """Called when a team draws a problem."""

    async def info_accepted(self, team, pb, still_available):
        """Called when a team accepts a problem."""

    async def info_rejected(self, team, pb, rnd):
        """Called when a team rejects a problem,
        before it is added to the rejected set."""


def setup(_):
    pass
