import itertools
import random
from operator import attrgetter

import discord
from discord.ext.commands import (
    Cog,
    command,
    Context,
    Bot,
    Command,
    CommandError,
    Group,
)

from src.constants import *


class MiscCog(Cog, name="Divers"):
    def __init__(self, bot: Bot):
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
        with open(JOKES_FILE) as f:
            jokes = f.read().split("\n\n\n")

        msg = random.choice(jokes)
        await ctx.send(msg)

    @command(name="help-test", aliases=["h"])
    async def help_test(self, ctx: Context, *args):
        """Affiche ce message"""

        if not args:
            await self.send_bot_help(ctx)
            return
        else:
            pass

        embed = discord.Embed(
            title="Help for `!draw`",
            description="Groupe qui continent des commande pour les tirages",
            color=0xFFA500,
        )
        # embed.set_author(name="*oooo*")
        embed.add_field(name="zoulou", value="okokok", inline=True)
        embed.add_field(name="lklk", value="mnmn", inline=True)
        embed.set_footer(text="thankss!")
        await ctx.send(embed=embed)

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
            key = lambda c: c.name

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
