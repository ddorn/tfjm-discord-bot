#!/bin/python

import os
import sys

import discord
from discord.ext import commands
import random

from discord.ext.commands import Context

TOKEN = os.environ.get("TFJM_DISCORD_TOKEN")

if TOKEN is None:
    print("No token for the bot were found.")
    print("You need to set the TFJM_DISCORD_TOKEN variable in your environement")
    print("Or just run:\n")
    print(f'    TFJM_DISCORD_TOKEN="your token here" python tfjm-discord-bot.py')
    print()
    quit(1)

GUILD = "690934836696973404"

bot = commands.Bot("!")


@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")


@bot.command(
    name="dice",
    help="Lance un dé à `n` faces. ",
    aliases=["de", "dé", "roll"],
    usage="n",
)
async def dice(ctx: Context, n: int):
    if n < 1:
        raise ValueError(f"Called dice with n={n}")

    dice = random.randint(1, n)
    await ctx.send(f"Le dé à {n} faces s'est arrêté sur... **{dice}**")


@bot.command(
    name="choose",
    help="Choisit une option parmi tous les arguments.",
    usage="choix1 choix2...",
    aliases=["choice", "choix", "ch"],
)
async def choose(ctx: Context, *args):
    choice = random.choice(args)
    await ctx.send(f"J'ai choisi... **{choice}**")


@bot.event
async def on_error(event, *args, **kwargs):
    print(event)
    print(*args)
    print(kwargs)

    raise


if __name__ == "__main__":
    bot.run(TOKEN)
