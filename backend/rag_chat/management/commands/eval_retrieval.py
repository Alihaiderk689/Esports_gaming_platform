from django.core.management.base import BaseCommand

from rag_chat.services.rerank_service import rerank
from rag_chat.services.retrieval_service import retrieve_candidates

# Each case is (question, substring expected to appear in the retrieved
# context, case_label). Substrings are grounded in text directly verified to
# exist in the uploaded rulebook PDF - not guessed. This is a small,
# hand-built regression set: run it after any change to chunking, retrieval,
# or re-ranking to see whether real fixes actually moved the needle, instead
# of relying on one-off manual queries.
EVAL_CASES = [
    ("How many players are in a match in pubg?", "100 players", "pubg_players_baseline"),
    ("How many players are in a match in pubg", "100 players", "pubg_players_no_question_mark"),
    ("how many players are in a match of pubg?", "100 players", "pubg_players_of_phrasing"),
    ("In Tekken, how many players fight in a single match?", "one-versus-one", "tekken_players"),
    ("How many players are on each team in League of Legends?", "five-versus-five", "lol_team_size"),
    ("What does PUBG stand for?", "PlayerUnknown's Battlegrounds", "pubg_full_name"),
]

TOP_K = 12


class Command(BaseCommand):
    help = "Run the hand-built retrieval eval set and report hit-rate + per-case rank of the expected content."

    def handle(self, *args, **options):
        hits = 0

        for question, expected_substring, label in EVAL_CASES:
            candidates, detected_game = retrieve_candidates(question)
            reranked = rerank(question, candidates, top_k=TOP_K)

            rank = None
            for i, chunk in enumerate(reranked, 1):
                if expected_substring.lower() in chunk.lower():
                    rank = i
                    break

            hit = rank is not None
            hits += hit

            status = self.style.SUCCESS(f"HIT  (rank {rank})") if hit else self.style.ERROR("MISS")
            self.stdout.write(
                f"[{label}] game={detected_game!r} candidates={len(candidates)} -> {status}"
            )
            self.stdout.write(f"    q: {question!r}")
            self.stdout.write(f"    expected: {expected_substring!r}")
            self.stdout.write("")

        total = len(EVAL_CASES)
        rate = (hits / total * 100) if total else 0
        self.stdout.write(self.style.WARNING(f"Hit-rate: {hits}/{total} ({rate:.0f}%)"))
