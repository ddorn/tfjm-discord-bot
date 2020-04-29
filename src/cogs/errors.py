import sys
import traceback

import discord
from discord.ext.commands import *
from discord.utils import maybe_coroutine

from src.errors import UnwantedCommand


# Global variable and function because I'm too lazy to make a metaclass
handlers = {}


def handles(error_type):
    """
    This registers an error handler.

    Error handlers can be coroutines or functions.
    """

    def decorator(f):
        handlers[error_type] = f
        return f

    return decorator


class ErrorsCog(Cog):
    """This cog defines all the handles for errors."""

    @Cog.listener()
    async def on_command_error(self, ctx: Context, error: CommandError):
        print(repr(error), file=sys.stderr)

        # We take the first superclass with an handler defined
        handler = None
        for type_ in error.__class__.__mro__:
            handler = handlers.get(type_)
            if handler:
                break

        if handler is None:
            # Default handling
            msg = repr(error)
        else:
            msg = await maybe_coroutine(handler, self, ctx, error)

        if msg:
            await ctx.send(msg)

    @handles(UnwantedCommand)
    async def on_unwanted_command(self, ctx, error):
        await ctx.message.delete()
        author: discord.Message
        await ctx.author.send(
            "J'ai supprimé ton message:\n> "
            + ctx.message.clean_content
            + "\nC'est pas grave, c'est juste pour ne pas encombrer "
            "le chat lors du tirage."
        )
        await ctx.author.send("Raison: " + error.original.msg)

    @handles(CommandInvokeError)
    async def on_command_invoke_error(self, ctx, error):
        specific_handler = handlers.get(type(error.original))

        if specific_handler:
            return await specific_handler(self, ctx, error)

        traceback.print_tb(error.original.__traceback__, file=sys.stderr)
        return (
            error.original.__class__.__name__
            + ": "
            + (str(error.original) or str(error))
        )

    @handles(CommandNotFound)
    def on_command_not_found(self, ctx, error):

        # Here we just take advantage that the error is formatted this way:
        # 'Command "NAME" is not found'
        name = str(error).partition('"')[2].rpartition('"')[0]
        return f"La commande {name} n'éxiste pas. Pour une liste des commandes, envoie `!help`."

    @handles(MissingRole)
    def on_missing_role(self, ctx, error):
        return (
            f"Il te faut le role de {error.missing_role} pour utiliser cette commande."
        )


def setup(bot):
    bot.add_cog(ErrorsCog())
