from sentence_transformers import CrossEncoder

# Lazy-loaded on first actual rerank() call, not at import time. This module
# gets imported just by resolving *any* URL (config/urls.py -> rag_chat.urls
# -> this), including completely unrelated endpoints like /api/core/health/ -
# eagerly loading a transformer model here coupled every request in the app
# to however long that load takes. On Render's free tier (0.1 CPU) that was
# slow enough to exceed gunicorn's worker timeout before the app ever
# finished booting, killing the worker mid-import and looping forever.
_model = None


def _get_model():
    global _model
    if _model is None:
        _model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _model


# Chunks scoring below this are noise, not just "less relevant" - observed
# score distributions put genuinely irrelevant chunks well below 0 and
# plausible-to-strong matches at 0.9+, so 0.0 is a conservative cutoff that
# only drops clear noise rather than borderline-useful content.
_MIN_SCORE = 0.0


def rerank(question, chunks, top_k=12, min_score=_MIN_SCORE):
    if not chunks:
        return []

    pairs = [[question, chunk] for chunk in chunks]
    scores = _get_model().predict(pairs)

    ranked = sorted(zip(chunks, scores), key=lambda pair: pair[1], reverse=True)
    return [chunk for chunk, score in ranked[:top_k] if score >= min_score]
