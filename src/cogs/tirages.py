#!/bin/python

import asyncio
import random
from collections import defaultdict, namedtuple
from io import StringIO
from pprint import pprint
from typing import Type

import discord
import yaml
from discord.ext import commands
from discord.ext.commands import group, Cog, Context
from discord.utils import get

from src.constants import *
from src.errors import TfjmError, UnwantedCommand

__all__ = ["Tirage", "TirageCog"]


def in_passage_order(teams, round=0):
    return sorted(teams, key=lambda team: team.passage_order[round] or 0, reverse=True)


Record = namedtuple("Record", ["name", "pb", "penalite"])


class Team(yaml.YAMLObject):
    yaml_tag = "Team"

    def __init__(self, ctx, team_role):
        self.name = team_role.name
        self.mention = team_role.mention
        self.tirage_order = [None, None]
        self.passage_order = [None, None]

        self.accepted_problems = [None, None]
        self.drawn_problem = None  # Waiting to be accepted or refused
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

    async def dice(self, ctx, n):
        if n != 100:
            raise UnwantedCommand(
                "C'est un dé à 100 faces qu'il faut tirer! (`!dice 100`)"
            )

        await self.phase.dice(ctx, ctx.author, random.randint(1, n))
        await self.update_phase(ctx)

    async def choose_problem(self, ctx):
        await self.phase.choose_problem(ctx, ctx.author)
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
        self.phase = None
        if False:
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
            f"A tout moment, ce rapport peut être envoyé avec `!draw show {len(tl) - 1}`"
        )

    def records(self, round):
        """Get the strings needed for show the tirage in a list of Records"""

        return [
            Record(
                team.name,
                (team.accepted_problems[round] or "- None")[0],
                f"k = {team.coeff(round)} ",
            )
            for team in in_passage_order(self.teams, round)
        ]

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
    | {1.name} |   Opp   |   Déf   |         |   Rap   |
    +-----+---------+---------+---------+---------+
    | {2.name} |   Rap   |   Opp   |   Déf   |         |
    +-----+---------+---------+---------+---------+
    | {3.name} |         |   Rap   |   Opp   |   Déf   |
    +-----+---------+---------+---------+---------+
```"""

        await ctx.send(msg)
        for round in (0, 1):
            msg = f"\n\n**{ROUND_NAMES[round].capitalize()}**:\n"
            msg += table.format(*self.records(round)) + "\n"
            for team in self.teams:
                msg += team.details(round)
            await ctx.send(msg)

    async def show_tex(self, ctx):
        if len(self.teams) == 3:
            table = r"""
\begin{{table}}[]
\begin{{tabular}}{{|c|c|c|c|}}
\hline
          & Phase 1 - {0.pb} & Phase 2 - {1.pb} & Phase {2.pb} \\\\ \hline
 {0.name} & Déf & Rap & Opp \\ \hline
 {1.name} & Opp & Déf & Rap \\ \hline
 {2.name} & Rap & Opp & Déf \\ \hline
\end{{tabular}}
\end{{table}}
"""
        else:
            table = r"""
            \begin{{table}}[]
            \begin{{tabular}}{{|c|c|c|c|c|}}
            \hline
                      & Phase 1 - {0.pb} & Phase 2 - {1.pb} & Phase 3 - {2.pb} & Phase 4 - {3.pb} \\\\ \hline
             {0.name} & Déf &     & Rap & Opp \\ \hline
             {1.name} & Opp & Déf &     & Rap \\ \hline
             {2.name} & Rap & Opp & Déf &     \\ \hline
             {3.name} &     & Rap & Opp & Déf \\ \hline
            \end{{tabular}}
            \end{{table}}
            """
        msg = ",tex "
        for i in (0, 1):
            msg += rf"\section{{ {ROUND_NAMES[i].capitalize()} }}"
            msg += table.format(*self.records(i))
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
        return get(ctx.guild.roles, name=Role.CAPTAIN).mention

    async def dice(self, ctx: Context, author, dice):
        raise UnwantedCommand()

    async def choose_problem(self, ctx: Context, author):
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

            teams_str = ", ".join(team.mention for team in re_do)
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

    async def choose_problem(self, ctx: Context, author):
        team = self.current_team
        if self.team_for(author) != team:
            raise UnwantedCommand(
                f"C'est à {team.name} de choisir " f"un problème, merci d'attendre :)"
            )

        assert (
            team.accepted_problems[self.round] is None
        ), "Choosing pb for a team that has a pb..."

        if team.drawn_problem:
            raise UnwantedCommand(
                "Vous avez déjà tiré un problème, merci de l'accepter (`!yes`) "
                "ou de le refuser (`!no)`."
            )

        # Choose an *available* problem
        problems = [
            p for p in PROBLEMS if self.available(p) and not p in team.accepted_problems
        ]
        problem = random.choice(problems)

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
            f"{self.current_team.mention} à toi l'honneur ! "
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

        await ctx.send(
            f"Les {self.captain_mention(ctx)}s, vous pouvez lancer "
            f"à nouveau un dé 100 (`!dice 100`)"
        )


class TirageOrderPhase(OrderPhase):
    """Phase to determine the tirage's order."""

    NEXT = PassageOrderPhase

    def __init__(self, tirage, round=0):
        super().__init__(tirage, round, "des tirages", "tirage_order", False)

    async def start(self, ctx):

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
            f"Les {self.captain_mention(ctx)}s, vous pouvez désormais lancer un dé 100 "
            "comme ceci `!dice 100`. "
            "L'ordre des tirages suivants sera l'ordre croissant des lancers. "
        )


class TirageCog(Cog, name="Tirages"):
    def __init__(self, bot):
        self.bot: commands.Bot = bot

        # We retrieve the global variable.
        # We don't want tirages to be ust an attribute
        # as we want them to outlive the Cog, for instance
        # if the cog is reloaded turing a tirage.
        from src.tfjm_discord_bot import tirages

        self.tirages = tirages

    # ---------- Commandes hors du groupe draw ----------- #

    @commands.command(
        name="dice", aliases=["de", "dé", "roll"], usage="n",
    )
    async def dice(self, ctx: Context, n: int):
        """Lance un dé à `n` faces."""
        channel = ctx.channel.id
        if channel in self.tirages:
            await self.tirages[channel].dice(ctx, n)
        else:
            if n < 1:
                raise TfjmError(f"Je ne peux pas lancer un dé à {n} faces, désolé.")

            dice = random.randint(1, n)
            await ctx.send(
                f"Le dé à {n} face{'s' * (n > 1)} s'est arrêté sur... **{dice}**"
            )

    @commands.command(
        name="random-problem",
        aliases=["rp", "problème-aléatoire", "probleme-aleatoire", "pa"],
    )
    async def random_problem(self, ctx: Context):
        """Choisit un problème parmi ceux de cette année."""

        channel = ctx.channel.id
        if channel in self.tirages:
            await self.tirages[channel].choose_problem(ctx)
        else:
            problem = random.choice(PROBLEMS)
            await ctx.send(f"Le problème tiré est... **{problem}**")

    @commands.command(
        name="oui", aliases=["accept", "yes", "o", "oh-yeaaah", "accepte", "ouiiiiiii"],
    )
    async def accept_cmd(self, ctx):
        """
        Accepte le problème qui vient d'être tiré.

        Sans effet si il n'y a pas de tirage en cours.
        """

        channel = ctx.channel.id
        if channel in self.tirages:
            await self.tirages[channel].accept(ctx, True)
        else:
            await ctx.send(f"{ctx.author.mention} approuve avec vigeur !")

    @commands.command(
        name="non", aliases=["refuse", "no", "n", "nope", "jaaamais"],
    )
    async def refuse_cmd(self, ctx):
        """
        Refuse le problème qui vient d'être tiré.

        Sans effet si il n'y a pas de tirage en cours.
        """

        channel = ctx.channel.id
        if channel in self.tirages:
            await self.tirages[channel].accept(ctx, False)
        else:
            await ctx.send(f"{ctx.author.mention} nie tout en bloc !")

    # ---------- Commandes du groupe draw ----------- #

    @group(name="draw", aliases=["d", "tirage"], invoke_without_command=True)
    async def draw_group(self, ctx: Context) -> None:
        """Groupe de commandes pour les tirages."""

        await ctx.invoke(self.bot.get_command("help"), "draw")

    @draw_group.command(
        name="start", usage="équipe1 équipe2 équipe3 (équipe4)",
    )
    @commands.has_any_role(*Role.ORGAS)
    async def start(self, ctx: Context, *teams: discord.Role):
        """
        (orga) Commence un tirage avec 3 ou 4 équipes.

        Cette commande attend des trigrames d'équipes.

        Exemple:
            `!draw start AAA BBB CCC`
        """

        channel: discord.TextChannel = ctx.channel
        channel_id = channel.id
        if channel_id in self.tirages:
            raise TfjmError(
                "Il y a déjà un tirage en cours sur cette channel, "
                "il est possible d'en commencer un autre sur une autre channel."
            )

        if len(teams) not in (3, 4):
            raise TfjmError(
                "Il faut 3 ou 4 équipes pour un tirage. "
                "Exemple: `!draw start @AAA @BBB @CCC`"
            )

        # Here all data should be valid

        # Prevent everyone from writing except Capitaines, Orga, CNO, Benevole
        if False:
            read = discord.PermissionOverwrite(send_messages=False)
            send = discord.PermissionOverwrite(send_messages=True)
            r = lambda role_name: get(ctx.guild.roles, name=role_name)
            overwrites = {
                ctx.guild.default_role: read,
                r(Role.CAPTAIN): send,
                r(Role.BENEVOLE): send,
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

        self.tirages[channel_id] = Tirage(ctx, channel_id, teams)
        await self.tirages[channel_id].phase.start(ctx)

    @draw_group.command(name="abort")
    @commands.has_any_role(*Role.ORGAS)
    async def abort_draw_cmd(self, ctx):
        """
        (orga) Annule le tirage en cours.

        Le tirage ne pourra pas être continué. Si besoin,
        n'hésitez pas à appeller un @dev : il peut réparer
        plus de choses qu'on imagine (mais moins qu'on voudrait).
        """
        channel_id = ctx.channel.id
        if channel_id in self.tirages:
            await self.tirages[channel_id].end(ctx)
            await ctx.send("Le tirage est annulé.")

    @draw_group.command(name="skip", aliases=["s"])
    @commands.has_role(Role.DEV)
    async def draw_skip(self, ctx, *teams: discord.Role):
        """(dev) Passe certaines phases du tirage."""
        channel = ctx.channel.id
        self.tirages[channel] = tirage = Tirage(ctx, channel, teams)

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

    @draw_group.command(name="show")
    async def show_cmd(self, ctx: Context, tirage_id: str = "all"):
        """
        Affiche le résumé d'un tirage.

        Exemples:
            `!draw show all` - Liste les ID possible
            `!draw show 42` - Affiche le tirage n°42
        """

        if not TIRAGES_FILE.exists():
            await ctx.send("Il n'y a pas encore eu de tirages.")
            return

        with open(TIRAGES_FILE) as f:
            tirages = list(yaml.load_all(f))

        if tirage_id.lower() == "all":
            await ctx.send(
                "Voici in liste de tous les tirages qui ont été faits et "
                "quelles équipes y on participé."
                "Vous pouvez en consulter un en particulier avec `!draw show ID`."
            )
            msg = "\n".join(
                f"`{i}`: {', '.join(team.name for team in tirage.teams)}"
                for i, tirage in enumerate(tirages)
            )
            await ctx.send(msg)
        else:
            try:
                n = int(tirage_id)
                if n < 0:
                    raise ValueError
                tirage = tirages[n]
            except (ValueError, IndexError):
                await ctx.send(
                    f"`{tirage_id}` n'est pas un identifiant valide. "
                    f"Les identifiants valides sont visibles avec `!draw show all`"
                )
            else:
                if False:
                    await tirage.show_tex(ctx)
                else:
                    await tirage.show(ctx)


def setup(bot):
    bot.add_cog(TirageCog(bot))
