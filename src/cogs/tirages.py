#!/bin/python
import random

import discord
import yaml
from discord.ext import commands
from discord.ext.commands import Context, group, Cog
from discord.utils import get

from src.cogs.tirage_logic import TiragePhase, Tirage
from src.constants import *
from src.errors import TfjmError


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

    @group(
        name="draw", aliases=["d", "tirage"],
    )
    async def draw_group(self, ctx: Context) -> None:
        """Groupe de commandes pour les tirages. Détails: `!help draw`"""

        print("WTFF")

    @draw_group.command(
        name="start", usage="équipe1 équipe2 équipe3 (équipe4)",
    )
    @commands.has_role(Role.ORGA)
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
    @commands.has_role(Role.ORGA)
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
                await tirage.show(ctx)


def setup(bot):
    bot.add_cog(TirageCog(bot))
