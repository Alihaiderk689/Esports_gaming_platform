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


def detect_games(text, known_names=None):
    """Every known game mentioned in `text`, canonicalized (see
    _canonical_name_map) and deduped, most-mentioned first. Unlike
    detect_game (a single best guess), this is what lets a caller notice a
    question genuinely names more than one game instead of silently
    collapsing to just one of them - see retrieval_service.retrieve_candidates,
    which scopes a Chroma query to every game returned here rather than only
    the top hit."""
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
        return []

    canonical_map = _canonical_name_map(_db_game_names())
    merged = {}
    # Iterates `counts` in the same order it was built (known_names' order,
    # longest name first) so canonicalizing "Tekken" into "Tekken 8" merges
    # into (rather than overwrites) a count "Tekken 8" already has of its own.
    for name, hits in counts.items():
        canonical = canonical_map.get(name, name)
        merged[canonical] = merged.get(canonical, 0) + hits

    # sorted() is stable, so a genuine tie preserves known_names' original
    # order - the same tie-break max() gave the single-best-guess case below.
    return sorted(merged, key=merged.get, reverse=True)


def detect_game(text, known_names=None):
    """The single best-guess game for `text` - back-compat wrapper around
    detect_games for callers that only ever want one answer (e.g.
    chunk_service.py tagging one rulebook section, which is never about more
    than one game at a time)."""
    games = detect_games(text, known_names)
    return games[0] if games else None
