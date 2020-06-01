import asyncio
import datetime
import io
import itertools
import random
import re
import urllib
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from functools import partial
from itertools import groupby
from math import log
from operator import attrgetter, itemgetter
from time import time
from typing import List, Set, Union

import aiohttp
import discord
import yaml
from discord import Guild, Member
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


HUG_RE = re.compile(r"^(?P<hugger>\d+) -> (?P<hugged>\d+) \| (?P<text>.*)$")


class Hug:
    def __init__(self, hugger, hugged, text):
        self.hugger = hugger
        self.hugged = hugged
        self.text = text

    @classmethod
    def from_str(cls, line: str):
        match = HUG_RE.match(line)
        if not match:
            raise ValueError(f"'{line}' is not a valid hug format.")
        hugger = int(match.group("hugger"))
        hugged = int(match.group("hugged"))
        text = match.group("text")

        return cls(hugger, hugged, text)

    def __repr__(self):
        return f"{self.hugger} -> {self.hugged} | {self.text}"


class MiscCog(Cog, name="Divers"):
    def __init__(self, bot: CustomBot):
        self.bot = bot
        self.show_hidden = False
        self.verify_checks = True
        self.computing = False
        self.hugs = self.get_hugs()

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

        if self.computing:
            return await ctx.send("Il y a déjà une fractale en cours de calcul...")

        try:
            self.computing = True

            await ctx.message.add_reaction(Emoji.CHECK)
            msg: discord.Message = ctx.message
            seed = msg.content[len("!fractal ") :]
            seed = seed or str(random.randint(0, 1_000_000_000))
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    FRACTAL_URL.format(seed=urllib.parse.quote(seed)), timeout=120
                ) as resp:
                    if resp.status != 200:
                        return await ctx.send(
                            "Il y a un problème pour calculer/télécharger l'image..."
                        )
                    data = io.BytesIO(await resp.read())
                    await ctx.send(
                        f"Seed: {seed}", file=discord.File(data, f"{seed}.png")
                    )
        finally:
            self.computing = False

    @command(hidden=True, aliases=["bang", "pan"])
    async def pew(self, ctx):
        await ctx.send("Tu t'es raté ! Kwaaack :duck:")

    @command(aliases=["pong"])
    async def ping(self, ctx):
        """Affiche la latence avec le bot."""
        msg: discord.Message = ctx.message
        ping = msg.created_at.timestamp()
        msg: discord.Message = await ctx.send("Pong !")
        pong = time()

        # 7200 is because we are UTC+2
        delta = pong - ping - 7200

        await msg.edit(content=f"Pong ! Ça a pris {int(1000 * (delta))}ms")

    @command(name="fan", aliases=["join", "adhere"], hidden=True)
    async def fan_club_cmd(self, ctx: Context, who: Member):
        """Permet de rejoindre un fan club existant."""
        role_id = FAN_CLUBS.get(who.id, None)
        role = get(ctx.guild.roles, id=role_id)

        if role is not None:
            await ctx.author.add_roles(role)
            await ctx.send(f"Bienvenue au {role.mention} !! :tada:")
        else:
            await ctx.send(
                f"{who.mention} n'a pas encore de fan club. Peut-être qu'un jour "
                f"iel sera un membre influent du CNO ?"
            )

    # ----------------- Hugs ---------------- #

    @command(aliases=["<3", "❤️", ":heart:", Emoji.RAINBOW_HEART])
    async def hug(self, ctx: Context, who="everyone"):
        """Fait un câlin à quelqu'un. :heart:"""

        if who == "everyone":
            who = ctx.guild.default_role
        elif who == "back":
            return await self.hug_back(ctx)
        else:
            try:
                who = await RoleConverter().convert(ctx, who)
            except BadArgument:
                try:
                    who = await MemberConverter().convert(ctx, who)
                except BadArgument:
                    return await ctx.send(
                        discord.utils.escape_mentions(
                            f'Il n\'y a pas de "{who}". :man_shrugging:'
                        )
                    )
        who: Union[discord.Role, Member]
        bot_hug = who == self.bot.user

        bonuses = [
            "C'est trop meuuuugnon !",
            "Ça remonte le moral ! :D",
            ":hugging:",
            ":smiling_face_with_3_hearts:",
            "Oh wiiii",
            # f"{'Je me sens' if bot_hug else 'Iel se sent'} désormais prêt à travailler à fond sur les solutions de AQT",
            f"{who.mention} en redemande un !"
            if not bot_hug
            else "J'en veux un autre ! :heart_eyes:",
            "Le·a pauvre, iel est tout·e rouge !"
            if not bot_hug
            else "Un robot ne peut pas rougir, mais je crois que... :blush:",
            "Hihi, il gratte ton pull en laine ! :sheep:",
        ]

        if (
            isinstance(who, discord.Member)
            and has_role(who, Role.JURY)
            and has_role(ctx.author, Role.PARTICIPANT)
        ):
            bonuses += ["Il s'agit surement là d'une tentative de corruption !"]

        if has_role(ctx.author, Role.PRETRESSE_CALINS):
            bonuses += [
                "C'est le plus beau calin du monde :smiling_face_with_3_hearts: :smiling_face_with_3_hearts:",
                f"{who.mention} est subjugué·e ! :smiling_face_with_3_hearts:",
            ]

        if who.id == DIEGO:
            bonuses += [
                "Tiens... Ça sent le mojito... :lemon:",
                ":green_heart: :lemon: :green_heart:",
            ]

        if who.id in FAN_CLUBS and not get(ctx.author.roles, id=FAN_CLUBS[who.id]):
            bonuses += ["Tu devrais rejoindre son fan club :wink:"]

        if who == ctx.author:
            msg = f"{who.mention} se fait un auto-calin !"
            bonuses += [
                "Mais c'est un peu ridicule...",
                "Mais iel a les bras trop courts ! :cactus:",
                "Il en faut peu pour être heureux :wink:",
            ]
        elif who == ctx.guild.default_role:
            msg = f"{ctx.author.mention} fait un câlin a touuuut le monde !"
            bonuses += [
                "Ça fait beaucoup de gens pour un câlin !",
                "Plus on est, plus on est calins !",
                "C'est pas très COVID-19 tout ça !",
                "Tout le monde est heureux maintenant !",
            ]
        elif bot_hug:
            msg = f"{ctx.author.mention} me fait un gros câliiiiin !"
            bonuses += ["Je trouve ça très bienveillant <3"]
        else:
            msg = f"{ctx.author.mention} fait un gros câlin à {who.mention} !"
            bonuses += [
                f"Mais {who.mention} n'apprécie pas...",
                "Et ils s'en vont chasser des canards ensemble :wink:",
                "Oh ! Iel sent bon...",
                "Et moi quand est ce que j'ai le droit à un calin ?",
                f"{who.mention} a serré tellment fort qu'iel vous a coupé en deux :scream:",
                f"{who.mention} propose à {ctx.author.mention} de se revoir autour d'une :pizza: !",
                "Les drones du commissaire Winston passent par là et vous ordonnent d'arrêter.",
                "Après ce beau moment de tendresse, ils décident d'aller discuter en créant des puzzles.",
                f"{who.mention} se réfugie dans l'entrepôt d'Animath et bloque l'entrée avec un meuble.",
            ]

        bonus = random.choice(bonuses)

        text = f"{msg} {bonus}"
        self.add_hug(ctx.author.id, who.id, text)

        await ctx.send(text)

        if bot_hug and random.random() > 0.9:
            await asyncio.sleep(3.14159265358979323)
            ctx.author = get(ctx.guild.members, id=self.bot.user.id)
            await ctx.invoke(self.hug, "back")

    async def hug_back(self, ctx: Context):
        hugger = ctx.author.id

        last_hug: Hug = get(reversed(self.hugs), hugged=hugger)
        if not last_hug:
            return await ctx.send(
                f"Personne n'a jamais fait de calin à {ctx.author.mention}, il faut y remédier !"
            )

        if "coupé en deux" in last_hug.text:
            return await ctx.send(
                "Tu ne vas quand même pas faire un câlin à quelqu'un "
                "que tu viens de couper en deux !"
            )

        await ctx.invoke(self.hug, str(last_hug.hugger))

    @command(name="hug-stats", aliases=["hs"])
    @commands.has_role(Role.PRETRESSE_CALINS)
    async def hugs_stats_cmd(self, ctx: Context, who: Member = None):
        """(prêtresse des calins) Affiche qui est le plus câliné """

        if who is None:
            await self.send_all_hug_stats(ctx)
        else:
            await self.send_hugs_stats_for(ctx, who)

    async def send_all_hug_stats(self, ctx):
        medals = [
            ":first_place:",
            ":second_place:",
            ":third_place:",
            ":medal:",
            ":military_medal:",
        ]
        ranks = ["Gros Nounours", "Petit Panda", "Ours en peluche"]

        embed = discord.Embed(
            title="Prix du plus câliné",
            color=discord.Colour.magenta(),
            description=f"Nombre de total de câlins : {len(self.hugs)} {Emoji.HEART}",
        )

        everyone = ctx.guild.default_role.id
        everyone_hugs = 0
        everyone_diff = set()
        stats = Counter()
        diffs = defaultdict(set)
        for h in self.hugs:
            if h.hugged == everyone:
                everyone_hugs += 1
                everyone_diff.add(h.hugger)
            else:
                if h.hugged != h.hugger:
                    stats[h.hugged] += 1
                    diffs[h.hugged].add(h.hugger)

                role: discord.Role = get(ctx.guild.roles, id=h.hugged)
                if role is not None:
                    for m in role.members:
                        if m.id != h.hugger:
                            stats[m.id] += 1
                            diffs[m.id].add(h.hugger)

        for m, d in diffs.items():
            stats[m] += len(everyone_diff.union(d)) * 42 + everyone_hugs

        top = sorted(list(stats.items()), key=itemgetter(1), reverse=True)

        for i in range(3):
            m = medals[i]
            r = ranks[i]
            id, qte = top[i]
            who = self.name_for(ctx, id)

            embed.add_field(name=f"{m} - {r}", value=f"{who} : {qte}  :heart:")

        top4to7 = "\n ".join(
            f"{medals[3]} {self.name_for(ctx, id)} : {qte}  :orange_heart:"
            for id, qte in top[3:8]
        )
        embed.add_field(name="Apprenti peluche", value=top4to7)

        top8to13 = "\n".join(
            f"{medals[4]} {self.name_for(ctx, id)} : {qte}  :yellow_heart:"
            for id, qte in top[8:13]
        )
        embed.add_field(name="Pelote de laine de canard", value=top8to13)

        await ctx.send(embed=embed)

    async def send_hugs_stats_for(self, ctx: Context, who: discord.Member):

        given = self.hugs_given(ctx, who.id)
        received = self.hugs_received(ctx, who.id)
        auto = self.auto_hugs(ctx, who.id)
        cut = [h for h in given if "coupé en deux" in h.text]
        infos = {
            "Câlins donnés": (len(given), 1),
            "Câlins reçus": (len(received), 1),
            "Personnes câlinées": (len(set(h.hugged for h in given)), 20),
            "Câliné par": (len(set(h.hugger for h in received)), 30),
            "Auto-câlins": ((len(auto)), 3),
            "Morceaux": (len(cut), 30),
        }

        most_given = Counter(h.hugged for h in given).most_common(1)
        most_received = Counter(h.hugger for h in received).most_common(1)
        most_given = most_given[0] if most_given else (0, 0)
        most_received = most_received[0] if most_received else (0, 0)

        embed = discord.Embed(
            title=f"Câlins de {who.display_name}",
            color=discord.Colour.magenta(),
            description=(
                f"On peut dire que {who.mention} est très câlin·e, avec un score de "
                f"{self.score_for(ctx, who.id)}. Iel a beaucoup câliné "
                f"{self.name_for(ctx, most_given[0])} "
                f"*({most_given[1]} :heart:)* et "
                f"s'est beaucoup fait câliner par {self.name_for(ctx, most_received[0])} "
                f"*({most_received[1]} :heart:)* !"
            ),
        )
        user: discord.User = self.bot.get_user(who.id)
        embed.set_thumbnail(url=user.avatar_url)

        for f, (v, h_factor) in infos.items():
            heart = self.heart_for_stat(v * h_factor)
            if f == "Morceaux":
                v = 2 ** v
            embed.add_field(name=f, value=f"{v} {heart}")

        await ctx.send(embed=embed)

    def ris(self, ctx: Context, id, role_or_member_id):
        """Whether the id is the same member or a member that has the given role."""
        if id == role_or_member_id:
            return True

        member: Member = get(ctx.guild.members, id=id)

        if member is None:
            return False

        role = get(member.roles, id=role_or_member_id)

        return role is not None

    def heart_for_stat(self, v):
        hearts = [
            ":broken_heart:",
            ":green_heart:",
            ":yellow_heart:",
            ":orange_heart:",
            ":heart:",
            ":sparkling_heart:",
            Emoji.RAINBOW_HEART,
        ]

        if v <= 0:
            return hearts[0]
        elif v >= 5000:
            return hearts[-1]
        elif v >= 2000:
            return hearts[-2]
        else:
            return hearts[len(str(v))]

    def name_for(self, ctx, member_or_role_id):
        memb = ctx.guild.get_member(member_or_role_id)
        if memb is not None:
            name = memb.mention
        else:
            role = ctx.guild.get_role(member_or_role_id)
            if role is None:
                name = getattr(
                    self.bot.get_user(member_or_role_id), "mention", "Personne"
                )
            else:
                name = role.name

        return name

    def score_for(self, ctx, member_id):
        received = self.hugs_received(ctx, member_id)
        diffs = set(h.hugger for h in received)
        return 42 * len(diffs) + len(received)

    def hugs_given(self, ctx, who_id):
        eq = partial(self.ris, ctx, who_id)
        return [h for h in self.hugs if eq(h.hugger) and not eq(h.hugged)]

    def hugs_received(self, ctx, who_id):
        eq = partial(self.ris, ctx, who_id)
        return [h for h in self.hugs if eq(h.hugged) and not eq(h.hugger)]

    def auto_hugs(self, ctx, who_id):
        eq = partial(self.ris, ctx, who_id)
        return [h for h in self.hugs if eq(h.hugged) and eq(h.hugger)]

    def get_hugs(self):
        File.HUGS.touch()
        lines = File.HUGS.read_text().strip().splitlines()
        return [Hug.from_str(l) for l in lines]

    def add_hug(self, hugger: int, hugged: int, text):
        File.HUGS.touch()
        with open(File.HUGS, "a") as f:
            f.write(f"{hugger} -> {hugged} | {text}\n")
        self.hugs.append(Hug(hugger, hugged, text))

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

    @group(name="joke", invoke_without_command=True, case_insensitive=True)
    async def joke(self, ctx: Context):
        """Fait discretement une blague aléatoire."""

        m: discord.Message = ctx.message
        await m.delete()

        jokes = self.load_jokes()
        if False:
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
            file = discord.File(File.MEMES / joke.file)
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
            joke.file = str(f"{joke_id}-{file.filename}")
            await file.save(File.MEMES / joke.file)
        elif not msg.strip():
            return "Tu ne peux pas ajouter une blague vide..."

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
        end = start + 24 * 60 * 60 * 5  # 5 days
        while time() < end:

            try:
                reaction, user = await self.bot.wait_for(
                    "reaction_add", check=check, timeout=end - time()
                )
            except asyncio.TimeoutError:
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
    @commands.has_any_role(*Role.ORGA)
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

            name = who.display_name if who else "Inconnu"
            embed.add_field(
                name=f"{i} - {name} - {len(joke.likes)}", value=text
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
            cat = {c.qualified_name: c for c in cat}
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
