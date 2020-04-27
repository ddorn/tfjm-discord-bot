from collections import namedtuple

import discord
from discord.ext import commands
from discord.ext.commands import Cog, Bot, group, Context
from discord.utils import get, find

from src.constants import *


Team = namedtuple("Team", ["name", "trigram", "tournoi", "secret", "status"])


class TeamsCog(Cog, name="Teams"):
    def __init__(self):
        self.teams = self.load_teams()

    def load_teams(self):
        with open(TEAMS_FILE) as f:
            # first line is header
            lines = f.read().splitlines()[1:]
        teams = [
            Team(*[field.strip('"') for field in line.split(";")]) for line in lines
        ]
        return teams

    @group(name="team")
    async def team(self, ctx):
        """Groupe de commandes pour la gestion des équipes."""

    @team.command(name="create")
    async def create_team(self, ctx: Context, trigram, team_secret):
        await ctx.message.delete()

        team: Team = get(self.teams, trigram=trigram)
        role: discord.Role = get(ctx.guild.roles, name=trigram)
        captain_role = get(ctx.guild.roles, name=Role.CAPTAIN)

        if team is None:
            await ctx.send(
                f"{ctx.author.mention}: le trigram `{trigram}` "
                f"n'est pas valide. Es-tu sûr d'avoir le bon ?"
            )
        elif role is not None:
            # Team exists
            captain = find(lambda m: captain_role in m.roles, role.members)
            await ctx.send(
                f"{ctx.author.mention}: l'équipe {trigram} "
                f"existe déjà. Tu peux demander a ton capitaine "
                f"{captain.mention} de t'ajouter à l'équipe avec "
                f"`!team add {ctx.author.mention}`"
            )
        elif team_secret != team.secret:
            await ctx.send(
                f"{ctx.author.mention}: ton secret n'est pas valide, "
                f"Tu peux le trouver sur https://inscription.tfjm.org/mon-equipe."
            )
        else:
            # Team creation !

            await ctx.send(f"Creation de l'équipe {trigram} avec {team_secret} !")


def setup(bot: Bot):
    bot.add_cog(TeamsCog())
