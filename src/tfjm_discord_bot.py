#!/bin/python

from discord.ext import commands

from src.constants import *

# We allow "! " to catch people that put a space in their commands.
# It must be in first otherwise "!" always match first and the space is not recognised
bot = commands.Bot(("! ", "!"))

# Global variable to hold the tirages.
# We *want* it to be global so we can reload the tirages cog without
# removing all the running tirages
tirages = {}


@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")


bot.remove_command("help")
bot.load_extension("src.cogs.dev")
bot.load_extension("src.cogs.errors")
bot.load_extension("src.cogs.misc")
bot.load_extension("src.cogs.teams")
bot.load_extension("src.cogs.tirages")


if __name__ == "__main__":
    bot.run(TOKEN)
