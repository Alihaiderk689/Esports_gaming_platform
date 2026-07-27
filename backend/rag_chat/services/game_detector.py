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


def _db_game_names():
    return [n for n in Game.objects.values_list("name", flat=True) if n]


def get_known_game_names():
    names = set(_db_game_names()) | set(_COMMON_ESPORTS_GAMES)
    return sorted(names, key=len, reverse=True)


def _canonical_name_map(db_names):
    """Maps a shorter alias to the one catalog game name that contains it as
    a word (e.g. "Tekken" -> "Tekken 8", "PUBG" -> "PUBG Mobile"), so text
    that only ever says the short form still gets tagged with the game's
    real name. Every mention of the long form also counts as a mention of
    the short alias it contains, so raw hit-counting alone can never let
    "Tekken 8" outscore "Tekken" - this mapping is applied after counting,
    not as another candidate in the count itself. Skipped when more than one
    catalog game contains the same alias, since then the text doesn't tell
    us which one it means.
    """
    aliases = set(_COMMON_ESPORTS_GAMES) | set(db_names)
    canonical = {}
    for alias in aliases:
        pattern = r"\b" + re.escape(alias.lower()) + r"\b"
        matches = [n for n in db_names if n != alias and re.search(pattern, n.lower())]
        if len(matches) == 1:
            canonical[alias] = matches[0]
    return canonical


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

    best = max(counts, key=counts.get)
    return _canonical_name_map(_db_game_names()).get(best, best)
