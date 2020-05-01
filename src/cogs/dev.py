import asyncio
import code
from pprint import pprint

import discord
from discord import TextChannel, PermissionOverwrite
from discord.ext.commands import command, has_role, Bot, Cog
from discord.utils import get
from ptpython.repl import embed

from src.constants import *
from src.core import CustomBot

COGS_SHORTCUTS = {
    "d": "tirages",
    "e": "errors",
    "m": "misc",
    "t": "teams",
    "u": "src.utils",
    "v": "dev",
}

KeyboardInterrupt


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

        names = [name] if name else list(COGS_SHORTCUTS.values())

        for name in names:

            name = self.full_cog_name(name)

            try:
                self.bot.reload_extension(name)
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
    @command(name="setup", hidden=True)
    @has_role(Role.DEV)
    async def setup_roles(self, ctx):
        """
        (dev) Commande temporaire pour setup le serveur.
        """

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
        """Envoie un message."""
        await ctx.message.delete()
        await ctx.send(" ".join(msg))


def setup(bot: CustomBot):
    bot.add_cog(DevCog(bot))
