import os
from pathlib import Path
from time import time

__all__ = [
    "TOKEN",
    "Role",
    "PROBLEMS",
    "MAX_REFUSE",
    "ROUND_NAMES",
    "TEAMS_CHANNEL_CATEGORY",
    "DIEGO",
    "BOT",
    "TOURNOIS",
    "EMBED_COLOR",
    "FRACTAL_URL",
    "File",
    "Emoji",
]


TOKEN = os.environ.get("TFJM_DISCORD_TOKEN")

if TOKEN is None:
    print("No token for the bot were found.")
    print("You need to set the TFJM_DISCORD_TOKEN variable in your environement")
    print("Or just run:")
    print()
    print(f'    TFJM_DISCORD_TOKEN="your token here" python tfjm-discord-bot.py')
    print()
    quit(1)

GUILD = "690934836696973404"
DIEGO = 430566197868625920  # Mon id
BOT = 703305132300959754
TEAMS_CHANNEL_CATEGORY = "Channels d'équipes"
EMBED_COLOR = 0xFFA500
FRACTAL_URL = "https://thefractal.space/img/{seed}.png?size=1500"

ROUND_NAMES = ["premier tour", "deuxième tour"]
TOURNOIS = [
    "Lille",
    "Lyon",
    "Paris-Saclay",
    "Paris-Avignon-Est",
    "Tours",
    "Bordeaux",
    "Nancy",
    "Rennes",
]


class Role:
    CNO = "CNO"
    DEV = "dev"
    ORGA = "Orga"
    ORGAS = tuple(f"Orga {t}" for t in TOURNOIS)
    BENEVOLE = "Bénévole"
    CAPTAIN = "Capitaine"
    PARTICIPANT = "Participant"
    TOURIST = "Touriste"


class Emoji:
    JOY = "😂"
    SOB = "😭"
    BIN = "🗑️"
    DICE = "🎲"
    CHECK = "✅"
    PLUS_1 = "👍"
    MINUS_1 = "👎"


class File:
    TOP_LEVEL = Path(__file__).parent.parent
    TIRAGES = TOP_LEVEL / "data" / "tirages.yaml"
    TEAMS = TOP_LEVEL / "data" / "teams"
    JOKES = TOP_LEVEL / "data" / "jokes"
    JOKES_V2 = TOP_LEVEL / "data" / "jokesv2"


with open(File.TOP_LEVEL / "data" / "problems") as f:
    PROBLEMS = f.read().splitlines()
MAX_REFUSE = len(PROBLEMS) - 4  # -5 usually but not in 2020 because of covid-19


def setup(bot):
    # Just so we can reload the constants
    pass
