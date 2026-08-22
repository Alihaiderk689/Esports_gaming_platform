from sentence_transformers import SentenceTransformer

# Lazy-loaded on first actual generate_embeddings() call - see
# rerank_service.py's _get_model() for why this can't happen at import time:
# this module gets imported just by resolving *any* URL, including endpoints
# with nothing to do with the RAG assistant.
_model = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def generate_embeddings(text_chunks):

    """
    Generate embeddings for text chunks

    Input:
    [
        "chunk one text",
        "chunk two text"
    ]

    Output:
    [
        [0.23,0.45,...],
        [0.12,0.98,...]
    ]
    """

    embeddings = _get_model().encode(
        text_chunks,
        show_progress_bar=True,
        normalize_embeddings=True
    )


    return embeddings.tolist()