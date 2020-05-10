from functools import wraps

import psutil
from discord.ext.commands import Bot


def fg(text, color: int = 0xFFA500):
    r = color >> 16
    g = color >> 8 & 0xFF
    b = color & 0xFF
    return f"\033[38;2;{r};{g};{b}m{text}\033[m"


def french_join(l):
    l = list(l)
    start = ", ".join(l[:-1])
    return f"{start} et {l[-1]}"


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
