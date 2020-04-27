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
            guild: discord.Guild = ctx.guild
            team_role = await guild.create_role(
                name=trigram,
                color=discord.Colour.from_rgb(255, 255, 255),
                reason="Creation of a new team",
            )
            tournoi = get(guild.roles, name=team.tournoi)

            await ctx.author.add_roles(
                team_role, captain_role, tournoi, reason="Creation of team " + trigram
            )

            await ctx.send(
                f"L'équipe {team_role.mention} a été créée et son capitaine "
                f"est {ctx.author.mention}"
            )


def setup(bot: Bot):
    bot.add_cog(TeamsCog())
