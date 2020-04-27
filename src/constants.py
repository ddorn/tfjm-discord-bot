import os
from pathlib import Path

__all__ = [
    "TOKEN",
    "ORGA_ROLE",
    "CNO_ROLE",
    "BENEVOLE_ROLE",
    "CAPTAIN_ROLE",
    "PROBLEMS",
    "MAX_REFUSE",
    "ROUND_NAMES",
    "TIRAGES_FILE",
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
ORGA_ROLE = "Orga"
CNO_ROLE = "CNO"
BENEVOLE_ROLE = "Bénévole"
CAPTAIN_ROLE = "Capitaine"

with open("problems") as f:
    PROBLEMS = f.read().splitlines()
MAX_REFUSE = len(PROBLEMS) - 5

ROUND_NAMES = ["premier tour", "deuxième tour"]

TOP_LEVEL_DIR = Path(__file__).parent.parent
TIRAGES_FILE = TOP_LEVEL_DIR / "data" / "tirages.yaml"
