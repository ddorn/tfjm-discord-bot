#!/bin/python

import asyncio
import random
from collections import defaultdict, namedtuple
from dataclasses import dataclass
from functools import wraps
from io import StringIO
from pprint import pprint
from typing import Type, Dict, Union, Optional, List

import discord
import yaml
from discord.ext import commands
from discord.ext.commands import group, Cog, Context
from discord.utils import get

from src.base_tirage import BaseTirage
from src.constants import *
from src.core import CustomBot
from src.errors import TfjmError, UnwantedCommand

__all__ = ["Tirage", "TirageCog"]

from src.utils import send_and_bin, french_join


def in_passage_order(teams, round=0):
    return sorted(teams, key=lambda team: team.passage_order[round] or 0, reverse=True)


Record = namedtuple("Record", ["name", "pb", "penalite"])


def delete_and_pm(f):
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        await self.ctx.message.delete()
        await self.ctx.author.send(
            "J'ai supprimé ton message:\n> "
            + self.ctx.message.clean_content
            + "\nC'est pas grave, c'est juste pour ne pas encombrer "
            "le chat lors du tirage."
        )

        msg = await f(self, *args, **kwargs)
        if msg:
            await self.ctx.author.send(f"Raison: {msg}")


def send_all(f):
    @wraps(f)
    async def wrapper(self, *args, **kwargs):
        async for msg in f(self, *args, **kwargs):
            await self.ctx.send(msg)

    return wrapper


class DiscordTirage(BaseTirage):
    def __init__(self, ctx, *teams, fmt):
        super(DiscordTirage, self).__init__(*teams, fmt=fmt)
        self.ctx = ctx
        self.captain_mention = get(ctx.guild.roles, name=Role.CAPTAIN).mention

    def records(self, teams, rnd):
        """Get the strings needed for show the tirage in a list of Records"""

        return [
            Record(
                team.name,
                (team.accepted_problems[rnd] or "- None")[0],
                f"k = {team.coeff(rnd)} ",
            )
            for team in teams
        ]

    @delete_and_pm
    async def warn_unwanted(self, wanted: Type, got: Type):

        texts = {
            (int, str): "Il faut tirer un problème avec `!rp` et pas un dé.",
            (int, bool): "Il faut accepter `!oui` ou refuser `!non` "
            "le problème d'abord.",
            (str, int): "Tu dois lancer un dé (`!dice 100`), pas choisir un problème.",
            (str, bool): "Il faut accepter `!oui` ou refuser `!non` le "
            "problème avant d'en choisir un autre",
            (bool, str): "Tu es bien optimiste pour vouloir accepter un problème "
            "avant de l'avoir tiré !"
            if got
            else "Halte là ! Ce serait bien de tirer un problème d'abord... "
            "et peut-être qu'il te plaira :) ",
            (bool, int): "Il tirer un dé avec `!dice 100` d'abord.",
        }

        reason = texts.get((type(got), wanted))

        if reason is None:
            print(f"Weird, arguments for warn_unwanted were {wanted} and {got}")
            reason = "Je sais pas, le code ne devrait pas venir ici..."
        return reason

    @delete_and_pm
    async def warn_wrong_team(self, expected, got):
        return "ce n'était pas à ton tour."

    async def warn_colisions(self, collisions: List[str]):
        await self.ctx.send(
            f"Les equipes {french_join(collisions)} ont fait le même résultat "
            "et doivent relancer un dé. "
            "Le nouveau lancer effacera l'ancien."
        )

    @delete_and_pm
    async def warn_twice(self, typ: Type):

        if typ == int:
            return "Tu as déjà lancé un dé, pas besoin de le refaire ;)"

        print("Weird, DiscordTirage.warn_twice was called with", typ)
        return "Je sais pas, le code ne devrait pas venir ici..."

    @send_all
    async def start_make_poule(self, rnd):
        if rnd == 0:
            yield (
                f"Les {self.captain_mention}s, vous pouvez désormais tous lancer un dé 100 "
                "comme ceci : `!dice 100`. "
                "Les poules et l'ordre de passage lors du premier tour sera l'ordre croissant des dés, "
                "c'est-à-dire que le plus petit lancer sera le premier à passer dans la poule A."
            )
        else:
            yield (
                f"Les {self.captain_mention}s, vous pouvez à nouveau tous lancer un dé 100, "
                f"afin de déterminer les poules du second tour."
            )

    async def start_draw_order(self, poule):
        print(poule)

    async def start_select_pb(self, team):
        await self.ctx.send(f"C'est au tour de {team.mention} de choisir un problème.")

    async def annonce_poules(self, poules):
        print(poules)

    @send_all
    async def annonce_draw_order(self, order):
        order_str = "\n ".join(f"{i}) {tri}" for i, tri in enumerate(order))
        yield "L'ordre de tirage des problèmes pour ce tour est donc: \n" + order_str

    async def annonce_poule(self, poule):
        teams = [self.teams[tri] for tri in self.poules[poule]]

        if len(teams) == 3:
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

        embed = discord.Embed(
            title=f"Résumé du tirage entre {french_join([t.name for t in teams])}",
            color=EMBED_COLOR,
        )

        embed.add_field(
            name=ROUND_NAMES[poule.rnd].capitalize(),
            value=table.format(*self.records(teams, poule.rnd)),
            inline=False,
        )

        for team in teams:
            embed.add_field(
                name=team.name + " - " + team.accepted_problems[poule.rnd],
                value=team.details(poule.rnd),
                inline=True,
            )

        embed.set_footer(
            text="Ce tirage peut être affiché à tout moment avec `!draw show XXX`"
        )

        await self.ctx.send(embed=embed)

    @send_all
    async def info_start(self):
        yield (
            "Nous allons commencer le tirage des problèmes. "
            "Seuls les capitaines de chaque équipe peuvent désormais écrire ici. "
            "Merci de d'envoyer seulement ce que est nécessaire et suffisant au "
            "bon déroulement du tirage. Vous pouvez à tout moment poser toute question "
            "si quelque chose n'est pas clair ou ne va pas."
            "\n"
            "\n"
            "Pour plus de détails sur le déroulement du tirgae au sort, le règlement "
            "est accessible sur https://tfjm.org/reglement."
        )

        yield (
            "Nous allons d'abord tirer les poules et l'ordre de passage dans chaque tour "
            "avec toutes les équipes puis pour chaque poule de chaque tour, nous tirerons "
            "l'ordre de tirage pour le tour et les problèmes."
        )

    @send_all
    async def info_finish(self):
        yield "Le tirage est fini, merci à tout le monde !"
        yield (
            "Vous pouvez désormais trouver les problèmes que vous devrez opposer ou rapporter "
            "sur la page de votre équipe."
        )
        # TODO: Save it
        # TODO: make them available with the api

    async def info_draw_pb(self, team, pb, rnd):
        if pb in team.rejected[rnd]:
            await self.ctx.send(
                f"Vous avez déjà refusé **{pb}**, "
                f"vous pouvez le refuser à nouveau (`!non`) et "
                f"tirer immédiatement un nouveau problème "
                f"ou changer d'avis et l'accepter (`!oui`)."
            )
        else:
            if len(team.rejected[rnd]) >= MAX_REFUSE:
                await self.ctx.send(
                    f"Vous pouvez accepter ou refuser **{pb}** "
                    f"mais si vous choisissez de le refuser, il y "
                    f"aura une pénalité de 0.5 sur le multiplicateur du "
                    f"défenseur."
                )
            else:
                await self.ctx.send(
                    f"Vous pouvez accepter (`!oui`) ou refuser (`!non`) **{pb}**. "
                    f"Il reste {MAX_REFUSE - len(team.rejected[rnd])} refus sans pénalité "
                    f"pour {team.mention}."
                )

    async def info_accepted(self, team, pb):
        await self.ctx.send(
            f"L'équipe {team.mention} a accepté "
            f"**{pb}** ! Les autres équipes "
            f"ne peuvent plus l'accepter."
        )

    async def info_rejected(self, team, pb, rnd):
        msg = f"{team.mention} a refusé **{pb}** "
        if pb in team.rejected[rnd]:
            msg += "sans pénalité."
        else:
            msg += "!"
        await self.ctx.send(msg)


class Tirage(yaml.YAMLObject):
    yaml_tag = "Tirage"

    def __init__(self, ctx, channel, teams):
        assert len(teams) in (3, 4)

        self.channel: int = channel
        self.teams = [Team(team) for team in teams]
        self.phase = TirageOrderPhase(self, round=0)

    async def update_phase(self, ctx):
        if self.phase.finished():
            next_class = await self.phase.next(ctx)

            if next_class is None:
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

        tl = {}
        if File.TIRAGES.exists():
            with open(File.TIRAGES) as f:
                tl = yaml.load(f)
        else:
            File.TIRAGES.touch()

        key = max(0, *tl.keys()) + 1
        tl[key] = self
        with open(File.TIRAGES, "w") as f:
            yaml.dump(tl, f)

        await ctx.send(
            f"A tout moment, ce rapport peut " f"être envoyé avec `!draw show {key}`"
        )

        from src.tfjm_discord_bot import tirages

        if self.channel in tirages:
            del tirages[self.channel]

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
    ...


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
            pass
        else:
            if yes:
                team.accepted_problems[self.round] = team.drawn_problem
            else:
                team.rejected[self.round].add(team.drawn_problem)

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


class TirageCog(Cog, name="Tirages"):
    def __init__(self, bot):
        self.bot: CustomBot = bot

        # We retrieve the global variable.
        # We don't want tirages to be just an attribute
        # as we want them to outlive the Cog, for instance
        # if the cog is reloaded turing a tirage.
        from src.tfjm_discord_bot import tirages

        self.tirages = tirages

    # ---------- Commandes hors du groupe draw ----------- #

    @commands.command(
        name="dice", aliases=["de", "dé", "roll"], usage="n",
    )
    @send_and_bin
    async def dice(self, ctx: Context, n):
        """Lance un dé à `n` faces."""

        if not n:
            raise TfjmError("Tu dois préciser un nombre de faces :wink:")

        bases = {"0x": 16, "0b": 2, "0o": 8}

        base = bases.get(n[:2], 10)
        try:
            n = int(n, base)
        except ValueError:
            try:
                n = float(n)

                if abs(n) == float("inf"):
                    raise TfjmError("Alors là tu vises vraiment gros toi !")
                if n != n:  # NaN
                    raise TfjmError("Nan, ça je peux pas faire !")
                if not n.is_integer():
                    print(n)
                    raise TfjmError(
                        "Un dé avec des fractions de faces ? "
                        "Si tu me donnes un patron, je le lancerai !"
                    )

                n = int(n)
            except ValueError:
                raise TfjmError(
                    "Ton argument ne ressemble pas trop à un entier :thinking:"
                )

        channel = ctx.channel.id
        if channel in self.tirages:
            await self.tirages[channel].dice(ctx, n)
        else:
            if n == 0:
                raise TfjmError(f"Un dé sans faces ? Le concept m'intéresse...")
            if n < 1:
                raise TfjmError(
                    "Je n'ai pas encore de dés en antimatière, "
                    "désolé :man_shrugging:"
                )
            if len(str(n)) > 1900:
                raise TfjmError(
                    "Oulà... Je sais que la taille ça ne compte pas, "
                    "mais là il est vraiment gros ton dé !"
                )

            dice = random.randint(1, n)
            return f"{ctx.author.mention} : {Emoji.DICE} {dice}"

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
            print(self.tirages, channel_id)
            print(self.tirages[channel_id])

            await self.tirages[channel_id].end(ctx)
            await ctx.send("Le tirage est annulé.")
        else:
            await ctx.send("Il n'y a pas de tirage en cours.")

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

    def get_tirages(self) -> Dict[int, Tirage]:
        if not File.TIRAGES.exists():
            return {}

        with open(File.TIRAGES) as f:
            tirages = yaml.load(f)

        return tirages

    @draw_group.command(name="show")
    async def show_cmd(self, ctx: Context, tirage_id: str = "all"):
        """
        Affiche le résumé d'un tirage.

        Exemples:
            `!draw show all` - Liste les ID possible
            `!draw show 42` - Affiche le tirage n°42
        """

        tirages = self.get_tirages()

        if not tirages:
            return await ctx.send("Il n'y a pas encore eu de tirages.")

        if tirage_id.lower() == "all":
            await ctx.send(
                "Voici in liste de tous les tirages qui ont été faits et "
                "quelles équipes y on participé."
                "Vous pouvez en consulter un en particulier avec `!draw show ID`."
            )
            msg = "\n".join(
                f"`{key}`: {', '.join(team.name for team in tirage.teams)}"
                for key, tirage in tirages.items()
            )
            await ctx.send(msg)
        else:
            try:
                n = int(tirage_id)
                if n < 0:
                    raise ValueError
                tirage = tirages[n]
            except (ValueError, KeyError):
                await ctx.send(
                    f"`{tirage_id}` n'est pas un identifiant valide. "
                    f"Les identifiants valides sont visibles avec `!draw show all`"
                )
            else:
                await tirage.show(ctx)

    @draw_group.command(name="dump")
    @commands.has_role(Role.DEV)
    async def dump_cmd(self, ctx, tirage_id: int, round=0):
        """Affiche un résumé succint d'un tirage."""
        tirages = self.get_tirages()

        try:
            n = int(tirage_id)
            if n < 0:
                raise ValueError
            tirage = tirages[n]
        except (ValueError, KeyError):
            await ctx.send(
                f"`{tirage_id}` n'est pas un identifiant valide. "
                f"Les identifiants valides sont visibles avec `!draw show all`"
            )
        else:
            msg = ";".join(
                x for t in tirage.teams for x in (t.name, t.accepted_problems[round][0])
            )

            await ctx.send(msg)


def setup(bot):
    bot.add_cog(TirageCog(bot))
