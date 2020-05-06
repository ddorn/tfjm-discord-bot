#!/bin/python

import asyncio
import random
import sys
import traceback
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

from src.base_tirage import BaseTirage, Event, Poule
from src.constants import *
from src.core import CustomBot
from src.errors import TfjmError, UnwantedCommand

__all__ = ["TirageCog"]

from src.utils import send_and_bin, french_join


Record = namedtuple("Record", ["name", "pb", "penalite"])


def delete_and_pm(f):
    @wraps(f)
    async def wrapper(self, *args, **kwargs):
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

    return wrapper


def send_all(f):
    @wraps(f)
    async def wrapper(self, *args, **kwargs):
        async for msg in f(self, *args, **kwargs):
            await self.ctx.send(msg)

    return wrapper


def safe(f):
    @wraps(f)
    async def wrapper(*args, **kwargs):
        try:
            return await f(*args, **kwargs)
        except Exception as e:
            traceback.print_tb(e.__traceback__, file=sys.stderr)
            print(e)

    return wrapper


class DiscordTirage(BaseTirage):
    def __init__(self, ctx, *teams, fmt):
        super(DiscordTirage, self).__init__(*teams, fmt=fmt)
        self.ctx = ctx
        self.captain_mention = get(ctx.guild.roles, name=Role.CAPTAIN).mention

        ts = self.load_all()
        self.id = 1 + (max(ts) if ts else 0)
        self.save()

    @staticmethod
    def load_all():
        if not File.TIRAGES.exists():
            return {}

        with open(File.TIRAGES) as f:
            tirages = yaml.load(f)

        return tirages

    def save(self):
        ts = self.load_all()

        ctx = self.ctx
        queue = self.queue
        self.ctx = None
        self.queue = None
        ts[self.id] = self

        File.TIRAGES.touch()
        with open(File.TIRAGES, "w") as f:
            yaml.dump(ts, f)

        self.ctx = ctx
        self.queue = queue

    def team_for(self, author):
        for team in self.teams:
            if get(author.roles, name=team):
                return team
        return None

    def mention(self, trigram):
        return get(self.ctx.guild.roles, name=trigram).mention

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

    async def dice(self, ctx, n):
        self.ctx = ctx
        trigram = self.team_for(ctx.author)

        if trigram is None:
            await self.warn_wrong_team(None, None)
        elif n == 100:
            await super().dice(trigram)
        else:
            await self.warn_unwanted(int, int)

    async def rproblem(self, ctx):
        self.ctx = ctx
        trigram = self.team_for(ctx.author)

        if trigram is None:
            await self.warn_wrong_team(None, None)
        else:
            await super().rproblem(trigram)

    async def accept(self, ctx, yes):
        self.ctx = ctx
        trigram = self.team_for(ctx.author)

        if trigram is None:
            await self.warn_wrong_team(None, None)
        else:
            await super().accept(trigram, yes)

    @safe
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
            (int, int): "Il faut lancer un dé à 100 faces.",
            (str, str): f"'{got}' n'est pas un problème valide.",
        }

        reason = texts.get((type(got), wanted))

        if reason is None:
            print(f"Weird, arguments for warn_unwanted were {wanted} and {got}")
            reason = "Je sais pas, le code ne devrait pas venir ici..."
        return reason

    @safe
    @delete_and_pm
    async def warn_wrong_team(self, expected, got):
        return "ce n'était pas à ton tour."

    @safe
    async def warn_colisions(self, collisions: List[str]):
        await self.ctx.send(
            f"Les equipes {french_join(collisions)} ont fait le même résultat "
            "et doivent relancer un dé. "
            "Le nouveau lancer effacera l'ancien."
        )

    @safe
    @delete_and_pm
    async def warn_twice(self, typ: Type):

        if typ == int:
            return "Tu as déjà lancé un dé, pas besoin de le refaire ;)"

        print("Weird, DiscordTirage.warn_twice was called with", typ)
        return "Je sais pas, le code ne devrait pas venir ici..."

    @safe
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

    @safe
    @send_all
    async def start_draw_poule(self, poule):
        yield (
            f"Nous allons commencer le tirage pour la poule **{poule}** entre les "
            f"équipes {french_join('**%s**' %p for p in self.poules[poule])}. Les autres équipes peuvent "
            f"quitter le salon si elles le souhaitent et revenir quand elles seront mentionnées."
        )

    @safe
    @send_all
    async def start_draw_order(self, poule):
        mentions = [self.mention(tri) for tri in self.poules[poule]]
        yield (
            f"Les capitaines de {french_join(mentions)}, vous pouvez à nouveau lancer un dé 100, "
            f"qui déterminera l'ordre de tirage des problèmes. Le plus grand lancer tirera en premier "
            f"les problèmes."
        )

    @safe
    async def start_select_pb(self, team):
        await self.ctx.send(f"C'est au tour de {team.mention} de choisir un problème.")

    @safe
    @send_all
    async def annonce_poules(self, poules):
        first = "\n".join(
            f"{p}: {french_join(t)}" for p, t in poules.items() if p.rnd == 0
        )
        second = "\n".join(
            f"{p}: {french_join(t)}" for p, t in poules.items() if p.rnd == 1
        )
        yield (
            f"Les poules sont donc, pour le premier tour :"
            f"```{first}```\n"
            f"Et pour le second tour :"
            f"```{second}```"
        )

    @safe
    @send_all
    async def annonce_draw_order(self, order):
        order_str = "\n".join(f"{i+1}) {tri}" for i, tri in enumerate(order))
        yield f"L'ordre de tirage des problèmes pour ce tour est donc: ```{order_str}```"

    @safe
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
+-----+---------+---------+---------+```"""
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
+-----+---------+---------+---------+---------+```"""

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
            text=f"Ce tirage peut être affiché à tout moment avec `!draw show {self.id}`"
        )

        await self.ctx.send(embed=embed)

        self.save()

    @safe
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

    @safe
    @send_all
    async def info_finish(self):
        yield "Le tirage est fini, merci à tout le monde !"
        yield (
            "Vous pouvez désormais trouver les problèmes que vous devrez opposer ou rapporter "
            "sur la page de votre équipe."
        )
        # TODO: make them available with the api

    @safe
    @send_all
    async def info_dice(self, team, dice):
        yield f"L'équipe {team} a lancé un... {dice} :game_die:"

    @safe
    @send_all
    async def info_draw_pb(self, team, pb, rnd):

        yield (f"L'équipe {self.mention(team.name)} a tiré... **{pb}**")

        if pb in team.rejected[rnd]:
            yield (
                f"Vous avez déjà refusé **{pb}**, "
                f"vous pouvez le refuser à nouveau (`!non`) et "
                f"tirer immédiatement un nouveau problème "
                f"ou changer d'avis et l'accepter (`!oui`)."
            )
        else:
            if len(team.rejected[rnd]) >= MAX_REFUSE:
                yield (
                    f"Vous pouvez accepter ou refuser **{pb}** "
                    f"mais si vous choisissez de le refuser, il y "
                    f"aura une pénalité de 0.5 sur le multiplicateur du "
                    f"défenseur."
                )
            else:
                yield (
                    f"Vous pouvez l'accepter (`!oui`) ou le refuser (`!non`). "
                    f"Il reste {MAX_REFUSE - len(team.rejected[rnd])} refus sans pénalité "
                    f"pour {team.mention}."
                )

    @safe
    async def info_accepted(self, team, pb):
        await self.ctx.send(
            f"L'équipe {team.mention} a accepté "
            f"**{pb}** ! Les autres équipes "
            f"ne peuvent plus l'accepter."
        )

    @safe
    async def info_rejected(self, team, pb, rnd):
        msg = f"{team.mention} a refusé **{pb}** "
        if pb in team.rejected[rnd]:
            msg += "sans pénalité."
        else:
            msg += "!"
        await self.ctx.send(msg)

    async def show(self, ctx):
        self.ctx = ctx
        for poule in self.poules:
            await self.annonce_poule(poule)


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

    @commands.command(name="dice-all", aliases=["da"], hidden=True)
    @commands.has_role(Role.DEV)
    async def dice_all_cmd(self, ctx, *teams):
        channel = ctx.channel.id
        if channel in self.tirages:
            for t in teams:
                d = random.randint(1, 100)
                await self.tirages[channel].event(Event(t, d))

    @commands.command(
        name="random-problem",
        aliases=["rp", "problème-aléatoire", "probleme-aleatoire", "pa"],
    )
    async def random_problem(self, ctx: Context):
        """Choisit un problème parmi ceux de cette année."""

        channel = ctx.channel.id
        if channel in self.tirages:
            await self.tirages[channel].rproblem(ctx)
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
    async def start(self, ctx: Context, fmt, *teams: discord.Role):
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

        try:
            fmt = list(map(int, fmt.split("+")))
        except ValueError:
            raise TfjmError(
                "Le premier argument doit être le format du tournoi, "
                "par exemple `3+3` pour deux poules à trois équipes"
            )

        if not set(fmt).issubset({3, 4}):
            raise TfjmError("Seuls les poules à 3 ou 4 équipes sont suportées.")

        # Here all data should be valid

        self.tirages[channel_id] = DiscordTirage(ctx, *teams, fmt=fmt)

        await self.tirages[channel_id].run()

        if self.tirages[channel_id]:
            # Check if aborted in an other way
            del self.tirages[channel_id]

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
            del self.tirages[channel_id]
            await ctx.send("Le tirage est annulé.")
        else:
            await ctx.send("Il n'y a pas de tirage en cours.")

    #
    # @draw_group.command(name="skip", aliases=["s"])
    # @commands.has_role(Role.DEV)
    # async def draw_skip(self, ctx, *teams: discord.Role):
    #     """(dev) Passe certaines phases du tirage."""
    #     channel = ctx.channel.id
    #     self.tirages[channel] = tirage = Tirage(ctx, channel, teams)
    #
    #     tirage.phase = TiragePhase(tirage, round=1)
    #     for i, team in enumerate(tirage.teams):
    #         team.tirage_order = [i + 1, i + 1]
    #         team.passage_order = [i + 1, i + 1]
    #         team.accepted_problems = [PROBLEMS[i], PROBLEMS[-i - 1]]
    #     tirage.teams[0].rejected = [{PROBLEMS[3]}, set(PROBLEMS[4:8])]
    #     tirage.teams[1].rejected = [{PROBLEMS[7]}, set()]
    #
    #     await ctx.send(f"Skipping to {tirage.phase.__class__.__name__}.")
    #     await tirage.phase.start(ctx)
    #     await tirage.update_phase(ctx)

    def get_tirages(self) -> Dict[int, BaseTirage]:
        return DiscordTirage.load_all()

    def save_tirages(self, tirages):
        File.TIRAGES.touch()
        with open(File.TIRAGES, "w") as f:
            yaml.dump(tirages, f)

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
                f"`{key}`: {', '.join(tirage.teams)}" for key, tirage in tirages.items()
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
    async def dump_cmd(self, ctx, tirage_id: int, poule="A", round: int = 1):
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
            poule = get(tirage.poules, poule=poule, rnd=round - 1)
            msg = f"{round};" + ";".join(
                x
                for t in tirage.poules[poule]
                for x in (
                    tirage.teams[t].name,
                    tirage.teams[t].accepted_problems[round - 1][0],
                )
            )

            await ctx.send(msg)


def setup(bot):
    bot.add_cog(TirageCog(bot))
