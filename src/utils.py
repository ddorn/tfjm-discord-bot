import psutil
from discord import Message
from discord.ext.commands import Context, Bot


def has_role(member, role: str):
    """Return whether the member has a role with this name."""

    return any(r.name == role for r in member.roles)


async def send_and_bin(bot: Bot, ctx: Context, msg=None, *, embed=None):
    """Send a message and wait 5min for the author to delete it."""

    message: Message = await ctx.send(msg, embed=embed)

    await msg


def start_time():
    return psutil.Process().create_time()


def setup(bot):
    bot.send_and_bin = send_and_bin
