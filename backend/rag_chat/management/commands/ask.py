from django.core.management.base import BaseCommand

from rag_chat.services.groq_service import generate_answer
from rag_chat.services.prompt_service import build_context
from rag_chat.services.rerank_service import rerank
from rag_chat.services.retrieval_service import retrieve_candidates


class Command(BaseCommand):
    help = "Ask the RAG chatbot a question directly from the terminal, no auth or HTTP required."

    def add_arguments(self, parser):
        parser.add_argument("question", type=str, help="The question to ask")

    def handle(self, *args, **options):
        question = options["question"]

        candidate_chunks, detected_game = retrieve_candidates(question)
        chunks = rerank(question, candidate_chunks, top_k=8)
        context = build_context(chunks)
        answer = generate_answer(question, context)

        if detected_game:
            self.stdout.write(self.style.WARNING(f"(detected game: {detected_game})"))
        self.stdout.write(self.style.SUCCESS(answer))
