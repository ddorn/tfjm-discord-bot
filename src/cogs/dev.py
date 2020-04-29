import code
from pprint import pprint

import discord
from discord import Colour, TextChannel, PermissionOverwrite
from discord.ext.commands import command, has_role, Bot, has_any_role
from discord.ext.commands import Cog
from discord.utils import get

from src.constants import *


COGS_SHORTCUTS = {"d": "dev", "ts": "teams", "t": "tirages", "m": "misc", "e": "errors"}


class DevCog(Cog, name="Dev tools"):
    def __init__(self, bot: Bot):
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

        local = {
            **globals(),
            **locals(),
            "pprint": pprint,
            "_show": lambda o: print(*dir(o), sep="\n"),
            "__name__": "__console__",
            "__doc__": None,
        }

        code.interact(
            banner="Ne SURTOUT PAS FAIRE Ctrl+C !\n(TFJM² debugger)", local=local
        )
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
    async def reload_cmd(self, ctx, name):
        """
        (dev) Recharge une catégorie de commandes.

        A utiliser quand le code change. Arguments
        possibles: `teams`, `tirages`, `dev`.
        """

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

        return

        aide: TextChannel = get(guild.text_channels, name="aide")
        for t in TOURNOIS:
            orga = get(guild.roles, name=f"Orga {t}")
            jury = get(guild.roles, name=f"Jury {t}")
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


def setup(bot: Bot):
    bot.add_cog(DevCog(bot))
