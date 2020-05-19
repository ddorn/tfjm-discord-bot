import asyncio
import re
import traceback
from io import StringIO
from pprint import pprint

import discord
from discord import TextChannel, PermissionOverwrite, Message, ChannelType
from discord.ext.commands import (
    command,
    has_role,
    Bot,
    Cog,
    ExtensionNotLoaded,
    Context,
    is_owner,
)
from discord.utils import get
from ptpython.repl import embed

from src.constants import *
from src.core import CustomBot
from src.errors import TfjmError
from src.utils import fg, french_join

COGS_SHORTCUTS = {
    "bt": "src.base_tirage",
    "c": "src.constants",
    "d": "tirages",
    "e": "errors",
    "m": "misc",
    "t": "teams",
    "u": "src.utils",
    "v": "dev",
}

RE_QUERY = re.compile(
    r"^! ?e(val)? (`{1,3}py(thon)?\n)?(?P<query>.*?)\n?(`{1,3})?\n?$", re.DOTALL
)


class DevCog(Cog, name="Dev tools"):
    def __init__(self, bot: CustomBot):
        self.bot = bot

    @command(name="interrupt")
    @has_role(Role.DEV)
    async def interrupt_cmd(self, ctx):
        """
        (dev) Ouvre une console là où un @dev m'a lancé. :warning:

        A utiliser en dernier recours:
         - le bot sera inactif pendant ce temps.
         - toutes les commandes seront executées à sa reprise.
        """

        await ctx.send(
            "J'ai été arrêté et une console interactive a été ouverte là où je tourne. "
            "Toutes les commandes rateront tant que cette console est ouverte.\n"
            "Soyez rapides, je déteste les opérations à coeur ouvert... :confounded:"
        )

        # Utility functions

        def send(msg, channel=None):
            if isinstance(channel, int):
                channel = self.bot.get_channel(channel)

            channel = channel or ctx.channel
            asyncio.create_task(channel.send(msg))

        try:
            await embed(
                globals(), locals(), vi_mode=True, return_asyncio_coroutine=True
            )
        except EOFError:
            pass

        await ctx.send("Tout va mieux !")

    def full_cog_name(self, name):
        name = COGS_SHORTCUTS.get(name, name)
        if not "." in name:
            name = f"src.cogs.{name}"

        return name

    @command(
        name="reload", aliases=["r"], usage=f"[{'|'.join(COGS_SHORTCUTS.values())}]"
    )
    @has_role(Role.DEV)
    async def reload_cmd(self, ctx, name=None):
        """
        (dev) Recharge une catégorie de commandes.

        A utiliser quand le code change. Arguments
        possibles: `teams`, `tirages`, `dev`.
        """

        if name is None:
            self.bot.reload()
            await ctx.send(":tada: The bot was reloaded !")
            return

        name = self.full_cog_name(name)

        try:
            self.bot.reload_extension(name)
        except ExtensionNotLoaded:
            await ctx.invoke(self.load_cmd, name)
            return
        except:
            await ctx.send(f":grimacing: **{name}** n'a pas pu être rechargée.")
            raise
        else:
            await ctx.send(f":tada: L'extension **{name}** a bien été rechargée.")

    @command(name="load", aliases=["l"])
    @has_role(Role.DEV)
    async def load_cmd(self, ctx, name):
        """
        (dev) Ajoute une catégorie de commandes.

        Permet d'ajouter dynamiquement un cog sans redémarrer le bot.
        """
        name = self.full_cog_name(name)

        try:
            self.bot.load_extension(name)
        except:
            await ctx.send(f":grimacing: **{name}** n'a pas pu être chargée.")
            raise
        else:
            await ctx.send(f":tada: L'extension **{name}** a bien été ajoutée !")

    # noinspection PyUnreachableCode
    @command(name="setup")
    @has_role(Role.DEV)
    async def setup_roles(self, ctx: Context, *teams: discord.Role):
        """
        (dev) Commande temporaire pour setup le serveur.
        """
        return
        finalist = get(ctx.guild.roles, name=Role.FINALISTE)
        assert finalist

        for t in teams:
            m: discord.Member
            for m in t.members:
                await m.add_roles(finalist)

        await ctx.send(
            f"{french_join(t.mention for t in teams)} ont été ajouté en finale !"
        )

        return
        guild: discord.Guild = ctx.guild
        nothing = PermissionOverwrite(read_messages=False)
        see = PermissionOverwrite(read_messages=True)
        # orga = get(guild.roles, name=f"Orga {t}")

        for t in TOURNOIS[3:]:
            jury = get(guild.roles, name=f"Jury {t}")
            for p in "AB":
                await guild.create_voice_channel(
                    f"blabla-jury-poule-{p}",
                    overwrites={guild.default_role: nothing, jury: see},
                    category=get(guild.categories, name=t),
                )

        return

        aide: TextChannel = get(guild.text_channels, name="aide")
        for t in TOURNOIS:
            await aide.set_permissions(orga, overwrite=see)
            await aide.set_permissions(jury, overwrite=see)

        return

        tournois = {
            tournoi: get(guild.categories, name=tournoi) for tournoi in TOURNOIS
        }

        for ch in guild.text_channels:
            print(repr(ch.category))

        for tournoi, cat in tournois.items():
            if tournoi == "Lyon":
                continue

            jury_channel: TextChannel = get(
                guild.text_channels, category=cat, name="cro"
            )
            await jury_channel.delete()
            # jury = get(guild.roles, name=f"Jury {tournoi}")
            orga = get(guild.roles, name=f"Orga {tournoi}")
            ov = {
                guild.default_role: nothing,
                # jury: see,
                orga: see,
            }
            await guild.create_text_channel(
                f"cro-{tournoi}", category=cat, overwrites=ov
            )

            await ctx.send(str(jury_channel))

    @command(name="send")
    @has_role(Role.DEV)
    async def send_cmd(self, ctx, *msg):
        """(dev) Envoie un message."""
        await ctx.message.delete()
        await ctx.send(" ".join(msg))

    @command(name="del")
    @has_role(Role.CNO)
    async def del_range_cmd(self, ctx: Context, id1: Message, id2: Message):
        """
        (cno) Supprime les messages entre les deux IDs en argument.
        """
        channel: TextChannel = id1.channel
        to_delete = [
            message async for message in channel.history(before=id1, after=id2)
        ] + [id1, id2]
        await channel.delete_messages(to_delete)
        await ctx.message.delete()

    def eval(self, msg: Message) -> discord.Embed:
        guild: discord.Guild = msg.guild
        roles = guild.roles
        members = guild.members

        query = re.match(RE_QUERY, msg.content).group("query")

        if not query:
            raise TfjmError("No query found.")

        if "\n" in query:
            lines = query.splitlines()
            if "return" not in lines[-1] and "=" not in lines[-1]:
                lines[-1] = f"return {lines[-1]}"
            query = "\n    ".join(lines)
            query = f"def q():\n    {query}\nresp = q()"

        try:
            if "\n" in query:
                q = compile(query, filename="query.py", mode="exec")
                globs = {**globals(), **locals()}
                locs = {}
                exec(query, globs, locs)
                resp = locs["resp"]
            else:
                resp = eval(query, globals(), locals())
        except Exception as e:
            tb = StringIO()
            traceback.print_tb(e.__traceback__, file=tb)
            tb.seek(0)

            embed = discord.Embed(title=str(e), color=discord.Colour.red())
            embed.add_field(name="Query", value=f"```py\n{query}\n```", inline=False)
            embed.add_field(
                name="Traceback", value=f"```py\n{tb.read()}```", inline=False
            )
        else:
            out = StringIO()
            pprint(resp, out)
            out.seek(0)
            embed = discord.Embed(title="Result", color=discord.Colour.green())
            embed.add_field(name="Query", value=f"```py\n{query}```", inline=False)
            embed.add_field(name="Value", value=f"```py\n{out.read()}```", inline=False)
        embed.set_footer(text="You may edit your message.")
        return embed

    @command(name="eval", aliases=["e"])
    @is_owner()
    async def eval_cmd(self, ctx: Context):
        """"""
        embed = self.eval(ctx.message)
        resp = await ctx.send(embed=embed)

        def check(before, after):
            return after.id == ctx.message.id

        while True:
            try:
                before, after = await self.bot.wait_for(
                    "message_edit", check=check, timeout=600
                )
            except asyncio.TimeoutError:
                break

            embed = self.eval(after)
            await resp.edit(embed=embed)

        # Remove the "You may edit your message"
        embed.set_footer()
        try:
            await resp.edit(embed=embed)
        except discord.NotFound:
            pass

    @Cog.listener()
    async def on_message(self, msg: Message):
        ch: TextChannel = msg.channel
        if ch.type == ChannelType.private:
            m = f"""{fg(msg.author.name)}: {msg.content}
MSG_ID: {fg(msg.id, 0x03A678)}
CHA_ID: {fg(msg.channel.id, 0x03A678)}"""
            print(m)


def setup(bot: CustomBot):
    bot.add_cog(DevCog(bot))
