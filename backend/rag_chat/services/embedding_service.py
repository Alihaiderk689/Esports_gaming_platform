from sentence_transformers import SentenceTransformer


# Load model once
model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

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

    embeddings = model.encode(
        text_chunks,
        show_progress_bar=True,
        normalize_embeddings=True
    )


    return embeddings.tolist()