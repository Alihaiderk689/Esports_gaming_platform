import os

from groq import Groq



client = Groq(
    api_key=os.getenv(
        "GROQ_API_KEY"
    )
)

GUARDRAIL_MESSAGE = "I can only answer questions related to esports rules and the uploaded documents."


def generate_answer(
        question,
        context,
        history=None
):


    prompt = f"""
You are an esports assistant for Esports Pakistan.

Answer the user's question only using the provided context.

If the answer is not present in the context,
say:

"{GUARDRAIL_MESSAGE}"

Context:

{context}


Question:

{question}


Answer:
"""

    messages = [
        {
            "role": "system",
            "content": "You answer esports questions using provided documents.",
        },
    ]

    for turn in (history or []):
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})

    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(

        model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),

        messages=messages,

        temperature=0.2,

        max_tokens=1024,

    )


    return response.choices[0].message.content