from sentence_transformers import CrossEncoder

# Loaded once, mirrors the embedding_service.py pattern.
model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


# Chunks scoring below this are noise, not just "less relevant" - observed
# score distributions put genuinely irrelevant chunks well below 0 and
# plausible-to-strong matches at 0.9+, so 0.0 is a conservative cutoff that
# only drops clear noise rather than borderline-useful content.
_MIN_SCORE = 0.0


def rerank(question, chunks, top_k=8, min_score=_MIN_SCORE):
    if not chunks:
        return []

    pairs = [[question, chunk] for chunk in chunks]
    scores = model.predict(pairs)

    ranked = sorted(zip(chunks, scores), key=lambda pair: pair[1], reverse=True)
    return [chunk for chunk, score in ranked[:top_k] if score >= min_score]
