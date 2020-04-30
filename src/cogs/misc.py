import datetime
import itertools
import random
from operator import attrgetter
from time import time

import discord
from discord import Guild
from discord.ext import commands
from discord.ext.commands import (
    Cog,
    command,
    Context,
    Bot,
    Command,
    CommandError,
    Group,
)

from src import utils
from src.constants import *
from src.constants import Emoji
from src.core import CustomBot
from src.utils import has_role, start_time


class MiscCog(Cog, name="Divers"):
    def __init__(self, bot: CustomBot):
        self.bot = bot
        self.show_hidden = False
        self.verify_checks = True

    @command(
        name="choose",
        usage='choix1 choix2 "choix 3"...',
        aliases=["choice", "choix", "ch"],
    )
    async def choose(self, ctx: Context, *args):
        """
        Choisit une option parmi tous les arguments.

        Pour les options qui contiennent une espace,
        il suffit de mettre des guillemets (`"`) autour.
        """

        choice = random.choice(args)
        await ctx.send(f"J'ai choisi... **{choice}**")

    @command(name="joke", aliases=["blague"], hidden=True)
    async def joke_cmd(self, ctx):
        await ctx.message.delete()
        with open(File.JOKES) as f:
            jokes = f.read().split("---")

        msg = random.choice(jokes)
        message: discord.Message = await ctx.send(msg)

        await message.add_reaction(Emoji.JOY)
        await message.add_reaction(Emoji.SOB)
        await self.bot.wait_for_bin(ctx.message.author, message)

    @command(name="status")
    @commands.has_role(Role.CNO)
    async def status_cmd(self, ctx: Context):
        """(cno) Affiche des informations à propos du serveur."""
        guild: Guild = ctx.guild
        embed = discord.Embed(title="État du serveur", color=EMBED_COLOR)
        benevoles = [g for g in guild.members if has_role(g, Role.BENEVOLE)]
        participants = [g for g in guild.members if has_role(g, Role.PARTICIPANT)]
        no_role = [g for g in guild.members if g.top_role == guild.default_role]
        uptime = datetime.timedelta(seconds=round(time() - start_time()))

        infos = {
            "Bénévoles": len(benevoles),
            "Participants": len(participants),
            "Sans rôle": len(no_role),
            "Total": len(guild.members),
            "Bot uptime": uptime,
        }

        width = max(map(len, infos))
        txt = "\n".join(
            f"`{key.rjust(width)}`: {value}" for key, value in infos.items()
        )
        embed.add_field(name="Stats", value=txt)

        await ctx.send(embed=embed)

    # ----------------- Help ---------------- #

    @command(name="help", aliases=["h"])
    async def help_cmd(self, ctx: Context, *args):
        """Affiche des détails à propos d'une commande."""

        if not args:
            await self.send_bot_help(ctx)
        else:
            await self.send_command_help(ctx, args)

    async def send_bot_help(self, ctx: Context):
        embed = discord.Embed(
            title="Aide pour le bot du TFJM²",
            description="Ici est une liste des commandes utiles (ou pas) "
            "durant le tournoi. Pour avoir plus de détails il "
            "suffit d'écrire `!help COMMANDE` en remplacant `COMMANDE` "
            "par le nom de la commande, par exemple `!help team channel`.",
            color=0xFFA500,
        )

        commands = itertools.groupby(self.bot.walk_commands(), attrgetter("cog_name"))

        for cat_name, cat in commands:
            cat = {c.qualified_name: c for c in cat if not isinstance(c, Group)}
            cat = await self.filter_commands(
                ctx, list(cat.values()), sort=True, key=attrgetter("qualified_name")
            )

            if not cat:
                continue

            names = ["!" + c.qualified_name for c in cat]
            width = max(map(len, names))
            names = [name.rjust(width) for name in names]
            short_help = [c.short_doc for c in cat]

            lines = [f"`{n}` - {h}" for n, h in zip(names, short_help)]

            if cat_name is None:
                cat_name = "Autres"

            c: Command
            text = "\n".join(lines)
            embed.add_field(name=cat_name, value=text, inline=False)

        embed.set_footer(text="Suggestion ? Problème ? Envoie un message à @Diego")

        await ctx.send(embed=embed)

    async def send_command_help(self, ctx, args):
        name = " ".join(args)
        comm: Command = self.bot.get_command(name)
        if comm is None:
            return await ctx.send(
                f"La commande `!{name}` n'existe pas. "
                f"Utilise `!help` pour une liste des commandes."
            )
        elif isinstance(comm, Group):
            return await self.send_group_help(ctx, comm)

        embed = discord.Embed(
            title=f"Aide pour la commande `!{comm.qualified_name}`",
            description=comm.help,
            color=0xFFA500,
        )

        if comm.aliases:
            aliases = ", ".join(f"`{a}`" for a in comm.aliases)
            embed.add_field(name="Alias", value=aliases, inline=True)
        if comm.signature:
            embed.add_field(
                name="Usage", value=f"`!{comm.qualified_name} {comm.signature}`"
            )
        embed.set_footer(text="Suggestion ? Problème ? Envoie un message à @Diego")

        await ctx.send(embed=embed)

    async def send_group_help(self, ctx, group: Group):
        embed = discord.Embed(
            title=f"Aide pour le groupe de commandes `!{group.qualified_name}`",
            description=group.help,
            color=0xFFA500,
        )

        comms = await self.filter_commands(ctx, group.commands, sort=True)
        if not comms:
            embed.add_field(
                name="Désolé", value="Il n'y a aucune commande pour toi ici."
            )
        else:
            names = ["!" + c.qualified_name for c in comms]
            width = max(map(len, names))
            just_names = [name.rjust(width) for name in names]
            short_help = [c.short_doc for c in comms]

            lines = [f"`{n}` - {h}" for n, h in zip(just_names, short_help)]

            c: Command
            text = "\n".join(lines)
            embed.add_field(name="Sous-commandes", value=text, inline=False)

            if group.aliases:
                aliases = ", ".join(f"`{a}`" for a in group.aliases)
                embed.add_field(name="Alias", value=aliases, inline=True)
            if group.signature:
                embed.add_field(
                    name="Usage", value=f"`!{group.qualified_name} {group.signature}`"
                )

            embed.add_field(
                name="Plus d'aide",
                value=f"Pour plus de détails sur une commande, "
                f"il faut écrire `!help COMMANDE` en remplaçant "
                f"COMMANDE par le nom de la commande qui t'intéresse.\n"
                f"Exemple: `!help {random.choice(names)[1:]}`",
            )
        embed.set_footer(text="Suggestion ? Problème ? Envoie un message à @Diego")

        await ctx.send(embed=embed)

    def _name(self, command: Command):
        return f"`!{command.qualified_name}`"

    async def filter_commands(self, ctx, commands, *, sort=False, key=None):
        """|coro|

        Returns a filtered list of commands and optionally sorts them.

        This takes into account the :attr:`verify_checks` and :attr:`show_hidden`
        attributes.

        Parameters
        ------------
        commands: Iterable[:class:`Command`]
            An iterable of commands that are getting filtered.
        sort: :class:`bool`
            Whether to sort the result.
        key: Optional[Callable[:class:`Command`, Any]]
            An optional key function to pass to :func:`py:sorted` that
            takes a :class:`Command` as its sole parameter. If ``sort`` is
            passed as ``True`` then this will default as the command name.

        Returns
        ---------
        List[:class:`Command`]
            A list of commands that passed the filter.
        """

        if sort and key is None:
            key = lambda c: c.qualified_name

        iterator = (
            commands if self.show_hidden else filter(lambda c: not c.hidden, commands)
        )

        if not self.verify_checks:
            # if we do not need to verify the checks then we can just
            # run it straight through normally without using await.
            return sorted(iterator, key=key) if sort else list(iterator)

        # if we're here then we need to check every command if it can run
        async def predicate(cmd):
            try:
                return await cmd.can_run(ctx)
            except CommandError:
                return False

        ret = []
        for cmd in iterator:
            valid = await predicate(cmd)
            if valid:
                ret.append(cmd)

        if sort:
            ret.sort(key=key)
        return ret


def setup(bot: Bot):
    bot.add_cog(MiscCog(bot))
