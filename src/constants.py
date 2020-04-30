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
    "TOURNOIS",
    "EMBED_COLOR",
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
DIEGO = "Diego"  # Mon display name
TEAMS_CHANNEL_CATEGORY = "Channels d'équipes"
EMBED_COLOR = 0xFFA500
ROUND_NAMES = ["premier tour", "deuxième tour"]
TOURNOIS = [
    "Lille",
    "Lyon",
    "Paris-Saclay",
    "Avignon",
    "Paris-Est",
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


class Emoji:
    JOY = "😂"
    SOB = "😭"


class File:
    TOP_LEVEL = Path(__file__).parent.parent
    TIRAGES = TOP_LEVEL / "data" / "tirages.yaml"
    TEAMS = TOP_LEVEL / "data" / "teams"
    JOKES = TOP_LEVEL / "data" / "jokes"


with open(File.TOP_LEVEL / "data" / "problems") as f:
    PROBLEMS = f.read().splitlines()
MAX_REFUSE = len(PROBLEMS) - 4  # -5 usually but not in 2020 because of covid-19
