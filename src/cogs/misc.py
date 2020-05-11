import datetime
import io
import itertools
import random
from dataclasses import dataclass, field
from operator import attrgetter
from time import time
from typing import List, Set

import aiohttp
import discord
import yaml
from discord import Guild
from discord.ext import commands
from discord.ext.commands import (
    Cog,
    command,
    Context,
    Command,
    CommandError,
    Group,
    group,
    MemberConverter,
    BadArgument,
    RoleConverter,
)
from discord.utils import get

from src.constants import *
from src.constants import Emoji
from src.core import CustomBot
from src.errors import TfjmError
from src.utils import has_role, start_time, send_and_bin


@dataclass
class Joke(yaml.YAMLObject):
    yaml_tag = "Joke"
    yaml_dumper = yaml.SafeDumper
    yaml_loader = yaml.SafeLoader
    joke: str
    joker: int
    likes: Set[int] = field(default_factory=set)
    dislikes: Set[int] = field(default_factory=set)
    file: str = None


class MiscCog(Cog, name="Divers"):
    def __init__(self, bot: CustomBot):
        self.bot = bot
        self.show_hidden = False
        self.verify_checks = True

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
        msg = await ctx.send(f"J'ai choisi... **{choice}**")
        await self.bot.wait_for_bin(ctx.author, msg),

    @command(name="status")
    @commands.has_role(Role.CNO)
    async def status_cmd(self, ctx: Context):
        """(cno) Affiche des informations à propos du serveur."""
        guild: Guild = ctx.guild
        embed = discord.Embed(title="État du serveur", color=EMBED_COLOR)
        benevoles = [g for g in guild.members if has_role(g, Role.BENEVOLE)]
        participants = [g for g in guild.members if has_role(g, Role.PARTICIPANT)]
        no_role = [g for g in guild.members if g.top_role == guild.default_role]
        uptime = datetime.timedelta(seconds=round(time() - start_time()))
        text = len(guild.text_channels)
        vocal = len(guild.voice_channels)
        infos = {
            "Bénévoles": len(benevoles),
            "Participants": len(participants),
            "Sans rôle": len(no_role),
            "Total": len(guild.members),
            "Salons texte": text,
            "Salons vocaux": vocal,
            "Bot uptime": uptime,
        }

        width = max(map(len, infos))
        txt = "\n".join(
            f"`{key.rjust(width)}`: {value}" for key, value in infos.items()
        )
        embed.add_field(name="Stats", value=txt)

        await ctx.send(embed=embed)

    @command(hidden=True)
    async def fractal(self, ctx: Context):
        await ctx.message.add_reaction(Emoji.CHECK)

        seed = random.randint(0, 1_000_000_000)
        async with aiohttp.ClientSession() as session:
            async with session.get(FRACTAL_URL.format(seed=seed)) as resp:
                if resp.status != 200:
                    return await ctx.send("Could not download file...")
                data = io.BytesIO(await resp.read())
                await ctx.send(file=discord.File(data, "cool_image.png"))

    @command(hidden=True, aliases=["bang", "pan"])
    async def pew(self, ctx):
        await ctx.send("Tu t'es raté ! Kwaaack :duck:")

    @command()
    async def hug(self, ctx, who):
        """Fait un câlin à quelqu'un."""

        if who != "everyone":
            try:
                who = await RoleConverter().convert(ctx, who)
            except BadArgument:
                try:
                    who = await MemberConverter().convert(ctx, who)
                except BadArgument:
                    return await ctx.send(
                        f'Je ne connais pas "{who}", verifie l\'orthographe '
                        f"et n'oublie pas les guillemets si il y a des espaces dans son nom. :wink:"
                    )

        bonuses = [
            "C'est trop meuuuugnon !",
            "Ça remonte le moral ! :D",
            ":hugging:",
            ":smiling_face_with_3_hearts:",
            "Oh wiiii",
        ]

        if who == ctx.author:
            msg = f"{who.mention} se fait un auto-calin !"
            bonuses += [
                "Mais c'est un peu ridicule...",
                "Mais il a les bras trop courts ! :cactus:",
                "Il en faut peu pour être heureux :wink:",
            ]
        elif who == "everyone" or who == ctx.guild.default_role:
            msg = f"{ctx.author.mention} fait un câlin a touuuut le monde !"
            bonuses += [
                "Ça fait beaucoup de gens pour un câlin !",
                "Plus on est, plus on est calins !",
                "C'est pas très COVID-19 tout ça !",
                "Tout le monde est heureux maintenant !",
            ]
        else:
            msg = f"{ctx.author.mention} fait un gros câlin à {who.mention} !"
            bonuses += [
                f"Mais {who.mention} n'apprécie pas...",
                "Et ils s'en vont chasser des canards ensemble :wink:",
                "Oh ! Il sent bon...",
            ]

        bonus = random.choice(bonuses)

        await ctx.send(f"{msg} {bonus}")

    @command(aliases=["pong"])
    async def ping(self, ctx):
        """Affiche la latence avec le bot."""
        ping = time()
        msg: discord.Message = await ctx.send("Pong !")
        pong = time()

        await msg.edit(content=f"Pong ! Ça a pris {int(1000 * (pong - ping))}ms")

    # ---------------- Jokes ---------------- #

    def load_jokes(self) -> List[Joke]:
        # Ensure it exists
        File.JOKES_V2.touch()
        with open(File.JOKES_V2) as f:
            jokes = list(yaml.safe_load_all(f))

        return jokes

    def save_jokes(self, jokes):
        File.JOKES_V2.touch()
        with open(File.JOKES_V2, "w") as f:
            yaml.safe_dump_all(jokes, f)

    @group(name="joke", invoke_without_command=True)
    async def joke(self, ctx: Context, id: int = None):

        m: discord.Message = ctx.message
        await m.delete()

        jokes = self.load_jokes()
        if id is not None:
            joke_id = id
            jokes = sorted(
                jokes, key=lambda j: len(j.likes) - len(j.dislikes), reverse=True
            )
        else:
            joke_id = random.randrange(len(jokes))

        try:
            joke = jokes[joke_id]
        except IndexError:
            raise TfjmError("Il n'y a pas de blague avec cet ID.")

        if joke.file:
            file = discord.File(joke.file)
        else:
            file = None

        message: discord.Message = await ctx.send(joke.joke, file=file)

        await message.add_reaction(Emoji.PLUS_1)
        await message.add_reaction(Emoji.MINUS_1)
        await self.wait_for_joke_reactions(joke_id, message)

    @joke.command(name="new")
    @send_and_bin
    async def new_joke(self, ctx: Context):
        """Ajoute une blague pour le concours de blague."""
        jokes = self.load_jokes()
        joke_id = len(jokes)

        author: discord.Member = ctx.author
        message: discord.Message = ctx.message

        msg = message.content[len("!joke new ") :]

        joke = Joke(msg, ctx.author.id, set())

        if message.attachments:
            file: discord.Attachment = message.attachments[0]
            joke.file = str(File.MEMES / f"{joke_id}-{file.filename}")
            await file.save(joke.file)

        jokes.append(joke)
        self.save_jokes(jokes)
        await message.add_reaction(Emoji.PLUS_1)
        await message.add_reaction(Emoji.MINUS_1)

        await self.wait_for_joke_reactions(joke_id, message)

    async def wait_for_joke_reactions(self, joke_id, message):
        def check(reaction: discord.Reaction, u):
            return (message.id == reaction.message.id) and str(reaction.emoji) in (
                Emoji.PLUS_1,
                Emoji.MINUS_1,
            )

        start = time()
        end = start + 24 * 60 * 60
        while time() < end:

            try:
                reaction, user = await self.bot.wait_for(
                    "reaction_add", check=check, timeout=end - time()
                )
            except TimeoutError:
                return

            if user.id == BOT:
                continue

            jokes = self.load_jokes()
            if str(reaction.emoji) == Emoji.PLUS_1:
                jokes[joke_id].likes.add(user.id)
            else:
                jokes[joke_id].dislikes.add(user.id)

            self.save_jokes(jokes)

    @joke.command(name="top", hidden=True)
    async def best_jokes(self, ctx: Context):
        """Affiche le palmares des blagues."""

        jokes = self.load_jokes()

        s = sorted(jokes, key=lambda j: len(j.likes) - len(j.dislikes), reverse=True)

        embed = discord.Embed(title="Palmares des blagues.")
        for i, joke in enumerate(s[:10]):
            who = get(ctx.guild.members, id=joke.joker)

            text = joke.joke
            if joke.file:
                text += " - image non inclue - "

            embed.add_field(
                name=f"{i} - {who.display_name} - {len(joke.likes)}", value=text
            )

        await ctx.send(embed=embed)

    # ----------------- Help ---------------- #

    @command(name="help", aliases=["h"])
    async def help_cmd(self, ctx: Context, *args):
        """Affiche des détails à propos d'une commande."""

        if not args:
            msg = await self.send_bot_help(ctx)
        else:
            msg = await self.send_command_help(ctx, args)

        await self.bot.wait_for_bin(ctx.author, msg)

    async def send_bot_help(self, ctx: Context):
        embed = discord.Embed(
            title="Aide pour le bot du TFJM²",
            description="Ici est une liste des commandes utiles (ou pas) "
            "durant le tournoi. Pour avoir plus de détails il "
            "suffit d'écrire `!help COMMANDE` en remplacant `COMMANDE` "
            "par le nom de la commande, par exemple `!help team channel`.",
            color=0xFFA500,
        )

        commands = itertools.groupby(self.bot.walk_commands(), attrgetter("cog_name"))

        for cat_name, cat in commands:
            cat = {c.qualified_name: c for c in cat if not isinstance(c, Group)}
            cat = await self.filter_commands(
                ctx, list(cat.values()), sort=True, key=attrgetter("qualified_name")
            )

            if not cat:
                continue

            names = ["!" + c.qualified_name for c in cat]
            width = max(map(len, names))
            names = [name.rjust(width) for name in names]
            short_help = [c.short_doc for c in cat]

            lines = [f"`{n}` - {h}" for n, h in zip(names, short_help)]

            if cat_name is None:
                cat_name = "Autres"

            c: Command
            text = "\n".join(lines)
            embed.add_field(name=cat_name, value=text, inline=False)

        embed.set_footer(text="Suggestion ? Problème ? Envoie un message à @Diego")

        return await ctx.send(embed=embed)

    async def send_command_help(self, ctx, args):
        name = " ".join(args).strip("!")
        comm: Command = self.bot.get_command(name)
        if comm is None:
            return await ctx.send(
                f"La commande `!{name}` n'existe pas. "
                f"Utilise `!help` pour une liste des commandes."
            )
        elif isinstance(comm, Group):
            return await self.send_group_help(ctx, comm)

        embed = discord.Embed(
            title=f"Aide pour la commande `!{comm.qualified_name}`",
            description=comm.help,
            color=0xFFA500,
        )

        if comm.aliases:
            aliases = ", ".join(f"`{a}`" for a in comm.aliases)
            embed.add_field(name="Alias", value=aliases, inline=True)
        if comm.signature:
            embed.add_field(
                name="Usage", value=f"`!{comm.qualified_name} {comm.signature}`"
            )
        embed.set_footer(text="Suggestion ? Problème ? Envoie un message à @Diego")

        return await ctx.send(embed=embed)

    async def send_group_help(self, ctx, group: Group):
        embed = discord.Embed(
            title=f"Aide pour le groupe de commandes `!{group.qualified_name}`",
            description=group.help,
            color=0xFFA500,
        )

        comms = await self.filter_commands(ctx, group.commands, sort=True)
        if not comms:
            embed.add_field(
                name="Désolé", value="Il n'y a aucune commande pour toi ici."
            )
        else:
            names = ["!" + c.qualified_name for c in comms]
            width = max(map(len, names))
            just_names = [name.rjust(width) for name in names]
            short_help = [c.short_doc for c in comms]

            lines = [f"`{n}` - {h}" for n, h in zip(just_names, short_help)]

            c: Command
            text = "\n".join(lines)
            embed.add_field(name="Sous-commandes", value=text, inline=False)

            if group.aliases:
                aliases = ", ".join(f"`{a}`" for a in group.aliases)
                embed.add_field(name="Alias", value=aliases, inline=True)
            if group.signature:
                embed.add_field(
                    name="Usage", value=f"`!{group.qualified_name} {group.signature}`"
                )

            embed.add_field(
                name="Plus d'aide",
                value=f"Pour plus de détails sur une commande, "
                f"il faut écrire `!help COMMANDE` en remplaçant "
                f"COMMANDE par le nom de la commande qui t'intéresse.\n"
                f"Exemple: `!help {random.choice(names)[1:]}`",
            )
        embed.set_footer(text="Suggestion ? Problème ? Envoie un message à @Diego")

        return await ctx.send(embed=embed)

    def _name(self, command: Command):
        return f"`!{command.qualified_name}`"

    async def filter_commands(self, ctx, commands, *, sort=False, key=None):
        """|coro|

        Returns a filtered list of commands and optionally sorts them.

        This takes into account the :attr:`verify_checks` and :attr:`show_hidden`
        attributes.

        Parameters
        ------------
        commands: Iterable[:class:`Command`]
            An iterable of commands that are getting filtered.
        sort: :class:`bool`
            Whether to sort the result.
        key: Optional[Callable[:class:`Command`, Any]]
            An optional key function to pass to :func:`py:sorted` that
            takes a :class:`Command` as its sole parameter. If ``sort`` is
            passed as ``True`` then this will default as the command name.

        Returns
        ---------
        List[:class:`Command`]
            A list of commands that passed the filter.
        """

        if sort and key is None:
            key = lambda c: c.qualified_name

        iterator = (
            commands if self.show_hidden else filter(lambda c: not c.hidden, commands)
        )

        if not self.verify_checks:
            # if we do not need to verify the checks then we can just
            # run it straight through normally without using await.
            return sorted(iterator, key=key) if sort else list(iterator)

        # if we're here then we need to check every command if it can run
        async def predicate(cmd):
            try:
                return await cmd.can_run(ctx)
            except CommandError:
                return False

        ret = []
        for cmd in iterator:
            valid = await predicate(cmd)
            if valid:
                ret.append(cmd)

        if sort:
            ret.sort(key=key)
        return ret


def setup(bot: CustomBot):
    bot.add_cog(MiscCog(bot))
