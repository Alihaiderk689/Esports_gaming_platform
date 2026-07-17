import os

import chromadb

_collection = None


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.CloudClient(
            api_key=os.getenv("CHROMA_API_KEY"),
            tenant=os.getenv("CHROMA_TENANT"),
            database=os.getenv("CHROMA_DATABASE"),
        )
        _collection = client.get_or_create_collection(
            name="esports_rules",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


_MAX_RECORDS_PER_ADD = 300


def add_chunks(rulebook_id, chunks, embeddings):
    ids = [f"{rulebook_id}_{i}" for i in range(len(chunks))]
    documents = [chunk["text"] for chunk in chunks]
    metadatas = [
        {
            "rulebook_id": rulebook_id,
            "game_name": chunk.get("game_name") or "",
            "heading": chunk.get("heading") or "",
            "subheading": chunk.get("subheading") or "",
            "page_start": chunk.get("page_start") or 0,
            "page_end": chunk.get("page_end") or 0,
        }
        for chunk in chunks
    ]

    collection = _get_collection()
    for start in range(0, len(documents), _MAX_RECORDS_PER_ADD):
        end = start + _MAX_RECORDS_PER_ADD
        collection.add(
            ids=ids[start:end],
            documents=documents[start:end],
            embeddings=embeddings[start:end],
            metadatas=metadatas[start:end],
        )


def delete_rulebook(rulebook_id):
    _get_collection().delete(where={"rulebook_id": rulebook_id})


def query(query_embedding, n_results=20, game_name=None):
    kwargs = {"query_embeddings": [query_embedding], "n_results": n_results}
    if game_name:
        kwargs["where"] = {"game_name": game_name}

    results = _get_collection().query(**kwargs)
    return results.get("documents", [[]])[0]


def keyword_query(keyword, n_results=10, game_name=None):
    kwargs = {"where_document": {"$contains": keyword}, "limit": n_results, "include": ["documents"]}
    if game_name:
        kwargs["where"] = {"game_name": game_name}

    results = _get_collection().get(**kwargs)
    return results.get("documents", [])
