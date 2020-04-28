import random

import discord
from discord.ext.commands import Cog, command, Context, Bot

from src.constants import *


class MiscCog(Cog, name="Divers"):
    def __init__(self, bot: Bot):
        self.bot = bot

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

    @command(
        name="help-test", hidden=True,
    )
    async def help_test(self, ctx: Context, *args):
        if not args:
            await self.send_bot_help(ctx)
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
        embed = discord.Embed(title="Aide pour le bot du TFJM²",)


def setup(bot: Bot):
    bot.add_cog(MiscCog(bot))
