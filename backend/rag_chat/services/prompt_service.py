# Rough character budget for the joined context passed to the LLM. Keeps a
# handful of near-max-size chunks from growing the prompt unboundedly.
_MAX_CONTEXT_CHARS = 6000


def build_context(chunks):
    if not chunks:
        return "No matching rules were found for this question."

    labeled = [f"[Source {i}]\n{chunk}" for i, chunk in enumerate(chunks, 1)]
    context = "\n\n".join(labeled)

    if len(context) > _MAX_CONTEXT_CHARS:
        context = context[:_MAX_CONTEXT_CHARS].rsplit("\n\n", 1)[0]

    return context
