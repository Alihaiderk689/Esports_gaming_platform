import re

from games.models import Game

# Fallback list so detection still works for games not yet registered as a
# Game row (e.g. a rulebook PDF can mention games nobody has created in the
# platform's catalog yet). Longest-name-first ordering happens in
# get_known_game_names() so "Call of Duty: Warzone" is tried before "Warzone".
_COMMON_ESPORTS_GAMES = [
    "PUBG", "PlayerUnknown's Battlegrounds", "Valorant", "League of Legends",
    "Apex Legends", "Call of Duty: Warzone", "Warzone", "Tekken", "Fortnite",
    "Counter-Strike", "CS:GO", "CS2", "Dota 2", "Overwatch", "Rainbow Six Siege",
    "Rocket League", "Street Fighter", "Mobile Legends", "Free Fire",
]


def get_known_game_names():
    db_names = list(Game.objects.values_list("name", flat=True))
    names = {n for n in db_names if n} | set(_COMMON_ESPORTS_GAMES)
    return sorted(names, key=len, reverse=True)


def detect_game(text, known_names=None):
    if known_names is None:
        known_names = get_known_game_names()

    lowered = text.lower()
    counts = {}
    for name in known_names:
        pattern = r"\b" + re.escape(name.lower()) + r"\b"
        hits = len(re.findall(pattern, lowered))
        if hits:
            counts[name] = hits

    if not counts:
        return None

    return max(counts, key=counts.get)
