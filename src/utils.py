from functools import wraps

import psutil
from discord.ext.commands import Bot


def has_role(member, role: str):
    """Return whether the member has a role with this name."""

    return any(r.name == role for r in member.roles)


def send_and_bin(f):
    """
    Decorator that allows a command in a cog to just return
    the messages that needs to be sent, and allow the author that
    trigger the message de delete it.
    """

    @wraps(f)
    async def wrapped(cog, ctx, *args, **kwargs):
        msg = await f(cog, ctx, *args, **kwargs)
        if msg:
            msg = await ctx.send(msg)
            await cog.bot.wait_for_bin(ctx.author, msg)

    return wrapped


def start_time():
    return psutil.Process().create_time()


def setup(bot: Bot):
    pass
