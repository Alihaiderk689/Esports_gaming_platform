import re
from concurrent.futures import ThreadPoolExecutor

from rag_chat.services.chroma_service import keyword_query
from rag_chat.services.chroma_service import query as vector_query
from rag_chat.services.embedding_service import generate_embeddings
from rag_chat.services.game_detector import detect_games

_STOPWORDS = {
    "how", "many", "what", "is", "are", "the", "a", "an", "in", "of", "on",
    "to", "for", "do", "does", "i", "you", "can", "will", "when", "where",
    "which", "who", "whom", "and", "or", "match", "this", "that", "did",
    "was", "were", "be", "there", "your",
}


def _extract_keywords(question, limit=3):
    words = re.findall(r"[A-Za-z0-9']+", question.lower())
    keywords = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    return keywords[:limit]


def retrieve_candidates(question, n_vector=20, n_keyword=5, fallback_game=None):
    """Returns (candidate_chunk_texts, effective_game_name).

    Vector search and each keyword variant are independent Chroma Cloud
    network calls - run them concurrently instead of sequentially, since
    each round trip costs ~200-250ms and doing 5-7 of them one after another
    was adding roughly a second of pure network wait to every question.

    fallback_game carries the game from the previous conversation turn.
    Follow-ups often don't name a game at all ("what about substitutes?"),
    so without this the search runs unscoped across every game instead of
    staying on-topic.

    A question naming more than one game ("compare Tekken 8 and PUBG's
    substitution rules") scopes the Chroma query to *every* game named, not
    just whichever one detect_games ranks first - collapsing to one would
    silently answer a comparative question from a single game's rulebook
    with no signal to the caller that the other game was dropped. The
    returned effective_game_name is still a single value (the most-mentioned
    game) since that's what ChatHistory.game_name/fallback_game continuity
    for the *next* turn expects - only the retrieval scope itself is
    multi-game aware.
    """
    detected_games = detect_games(question)
    if len(detected_games) > 1:
        game_scope = detected_games
    else:
        # 0 or 1 detected games: a bare string/None, same shape retrieve_candidates
        # always passed before multi-game detection existed - only a genuine
        # multi-game question needs the list form at all.
        game_scope = detected_games[0] if detected_games else fallback_game
    game_name = detected_games[0] if detected_games else fallback_game

    query_embedding = generate_embeddings([question])[0]

    keywords = _extract_keywords(question)
    variants = [v for keyword in keywords for v in (keyword, keyword.capitalize())]

    with ThreadPoolExecutor(max_workers=1 + len(variants)) as pool:
        vector_future = pool.submit(vector_query, query_embedding, n_results=n_vector, game_name=game_scope)
        keyword_futures = [
            pool.submit(keyword_query, v, n_results=n_keyword, game_name=game_scope) for v in variants
        ]

        vector_candidates = vector_future.result()
        keyword_candidates = [chunk for future in keyword_futures for chunk in future.result()]

    seen = set()
    merged = []
    for chunk in vector_candidates + keyword_candidates:
        if chunk not in seen:
            seen.add(chunk)
            merged.append(chunk)

    return merged, game_name
