from collections import namedtuple
from typing import List, Tuple

import discord
from discord.ext import commands
from discord.ext.commands import Cog, Bot, group, Context
from discord.utils import get, find

from src.constants import *
from src.utils import has_role

Team = namedtuple("Team", ["name", "trigram", "tournoi", "secret", "status"])


class TeamsCog(Cog, name="Teams"):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.teams = self.load_teams()

    def load_teams(self):
        with open(File.TEAMS) as f:
            # first line is header
            lines = f.read().splitlines()[1:]
        teams = [
            Team(*[field.strip('"') for field in line.split(";")]) for line in lines
        ]
        return teams

    def teams_for(self, member) -> List[Tuple[Team, discord.Role]]:
        """Return a list of pairs (role, team) corresponding to the teams of the member"""

        teams = []
        for role in member.roles:
            team = get(self.teams, trigram=role.name)
            if team:
                teams.append((team, role))
        return teams

    @group(name="team", invoke_without_command=True)
    async def team(self, ctx):
        """Groupe de commandes pour la gestion des équipes."""

        await ctx.invoke(self.bot.get_command("help"), "team")

    @team.command(name="create")
    async def create_team(self, ctx: Context, trigram, team_secret):
        """
        Permet aux capitaines de créer leur equipes.

        Pour utiliser cette commande, il faut ton trigram et ton code
        d'équipe. Tu peux ensuite écrire `!team create TRIGRAM SECRET`
        en gradant le point d'éclamation et en remplaçant `TRIGRAM` et
        `SECRET` par les bonnes valeurs. Le message que tu envoie sera
        immédiatement supprimé pour pas que d'autres voient ton secret,
        donc ne t'inquiète pas si il disparait.

        Exemple:
            `!team create FOX abq23j`
        """

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
                f"`!team add {ctx.author.name}`"
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
            participant = get(guild.roles, name=Role.PARTICIPANT)

            await ctx.author.add_roles(
                team_role,
                captain_role,
                tournoi,
                participant,
                reason="Creation of team " + trigram,
            )

            await ctx.send(
                f"L'équipe {team_role.mention} a été créée et son capitaine "
                f"est {ctx.author.mention}"
            )

            diego = get(ctx.guild.members, display_name=DIEGO, top_role__name=Role.CNO)
            await ctx.author.send(
                f"Salut Capitaine !\n"
                "On va être amené à faire de nombreuses choses ensemble "
                "ces prochains jours, donc n'hésite pas à abuser de `!help`. "
                "Tu peux l'utiliser ici mais malheureusement tu ne pourra pas voir "
                "les commandes qui sont réservés aux capitaines. \n"
                "Une commande que tu peux avoir envie d'utiliser c'est "
                "`!team channel un-super-nom` pour créer une channel réservée à "
                "ton équipe. \n\n"
                f"Si tu as des suggestions pour que le bot permette à chacun d'avoir "
                f"une meilleure expérience ici, envoie un petit message à {diego.mention} ;)"
            )

    @team.command(name="add")
    @commands.has_role(Role.CAPTAIN)
    async def team_add(self, ctx, member: discord.Member):
        """
        (cap) Ajoute un membre a ton équipe.

        Commande réservée aux capitaines pour ajouter un
        membre dans leur équipe. Cela permet juste de donner
        les bons roles pour que les bonnes *channels* soient
        accessibles.

        Exemple:
            `!team add @Jean-Mich-Much`
        """

        author_teams = self.teams_for(ctx.author)
        member_teams = self.teams_for(member)

        if member_teams:
            await ctx.send(
                f"{member.mention} est déjà dans une équipe "
                f"et ne peut pas être dans deux à la fois."
            )
        elif len(author_teams) > 1:
            await ctx.send(
                f"Tu est dans plusieurs équipes, je ne sais "
                f"pas où l'ajouter. Il faut demander à un organisateur "
                f"de le faire."
            )
        else:
            the_team = author_teams[0]
            tournoi = get(ctx.guild.roles, name=the_team[0].tournoi)
            participant = get(ctx.guild.roles, name=Role.PARTICIPANT)

            await member.add_roles(
                the_team[1],
                tournoi,
                participant,
                reason=f"{ctx.author.name} l'a ajouté à son équipe",
            )
            await ctx.send(
                f"{member.mention} a été ajouté dans l'équipe {the_team[1].mention}"
            )

    @team.command(name="channel")
    @commands.has_role(Role.CAPTAIN)
    async def team_channel(self, ctx, *channel_name):
        """
        (cap) Crée une channel privée pour l'équipe

        Crée un endroit de discussion privé seulement pour l'équipe
        personne d'autre n'y aura accès.

        Exemple:
            `!team channel un-nom-sympa`
        """

        if not channel_name:
            await ctx.send(
                "Tu dois mettre un nom d'équipe, par exemple "
                "`!team channel un-super-nom`"
            )
            return

        channel_name = " ".join(channel_name)

        guild: discord.Guild = ctx.guild
        team_role = self.teams_for(ctx.author)[0][1]
        team_channel_category = get(guild.categories, name=TEAMS_CHANNEL_CATEGORY)
        await guild.create_text_channel(
            channel_name,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                team_role: discord.PermissionOverwrite(read_messages=True),
            },
            category=team_channel_category,
            reason=f"{ctx.author.name} à demandé une channel pour son équipe.",
        )

    @team.command(name="voice", usage="Nom du salon")
    @commands.has_role(Role.CAPTAIN)
    async def team_voice(self, ctx, *channel_name):
        """
        (cap) Crée une channel vocale privée pour l'équipe

        Crée un endroit de discussion privé seulement pour l'équipe
        personne d'autre n'y aura accès.

        Exemple:
            `!team voice un-nom-sympa`
        """

        if not channel_name:
            await ctx.send(
                "Tu dois mettre un nom d'équipe, par exemple "
                "`!team voice un-super-nom`"
            )
            return

        channel_name = " ".join(channel_name)

        guild: discord.Guild = ctx.guild
        team_role = self.teams_for(ctx.author)[0][1]
        team_channel_category = get(guild.categories, name=TEAMS_CHANNEL_CATEGORY)
        await guild.create_voice_channel(
            channel_name,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                team_role: discord.PermissionOverwrite(read_messages=True),
            },
            category=team_channel_category,
            reason=f"{ctx.author.name} à demandé un salon vocale pour son équipe.",
        )

    @team.command(name="list")
    @commands.has_role(Role.CNO)
    async def list_cmd(self, ctx):
        """(cno) Affiche les équipes de chaque tournoi présentes sur le discord."""

        embed = discord.Embed(title="Liste des équipes", color=EMBED_COLOR)

        captains = [m for m in ctx.guild.members if has_role(m, Role.CAPTAIN)]
        tournois = {
            tournoi: [c for c in captains if has_role(c, tournoi)]
            for tournoi in TOURNOIS
        }

        for tournoi, caps in tournois.items():
            # we assume captains have exactly one team.
            txt = "\n".join(self.teams_for(c)[0][0].trigram for c in caps)
            txt = txt or "Il n'y a pas encore d'équipes sur le discord."
            embed.add_field(name=tournoi, value=txt)

        await ctx.send(embed=embed)


def setup(bot: Bot):
    bot.add_cog(TeamsCog(bot))
