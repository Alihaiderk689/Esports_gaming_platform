import json
import os

from django.core.management.base import BaseCommand

from rag_chat.services.chroma_service import keyword_query
from rag_chat.services.groq_service import generate_answer
from rag_chat.services.prompt_service import build_context
from rag_chat.services.rerank_service import rerank
from rag_chat.services.retrieval_service import retrieve_candidates

# Each case pairs a question with an expected_substring that is verified to
# exist, verbatim, somewhere in the uploaded rulebook PDF (carried over from
# eval_retrieval.py - not guessed), plus a short reference answer used as the
# RAGAS ground truth. Extend this list with more verified (question,
# substring, reference) triples as the rulebook corpus grows.
EVAL_CASES = [
    {
        "label": "pubg_players_baseline",
        "question": "How many players are in a match in pubg?",
        "expected_substring": "100 players",
        "reference": "A PUBG match has 100 players.",
    },
    {
        "label": "pubg_players_no_question_mark",
        "question": "How many players are in a match in pubg",
        "expected_substring": "100 players",
        "reference": "A PUBG match has 100 players.",
    },
    {
        "label": "pubg_players_of_phrasing",
        "question": "how many players are in a match of pubg?",
        "expected_substring": "100 players",
        "reference": "A PUBG match has 100 players.",
    },
    {
        "label": "tekken_players",
        "question": "In Tekken, how many players fight in a single match?",
        "expected_substring": "one-versus-one",
        "reference": "Tekken matches are one-versus-one.",
    },
    {
        "label": "lol_team_size",
        "question": "How many players are on each team in League of Legends?",
        "expected_substring": "five-versus-five",
        "reference": "League of Legends teams are five-versus-five.",
    },
    {
        "label": "pubg_full_name",
        "question": "What does PUBG stand for?",
        "expected_substring": "PlayerUnknown's Battlegrounds",
        "reference": "PUBG stands for PlayerUnknown's Battlegrounds.",
    },
]

DEFAULT_K = 12  # matches TOP_K used by ChatView / ask.py in production
# Defaults to the same model the app already uses for generation (GROQ_MODEL)
# rather than a bigger judge model - Groq's free tier caps tokens per day
# *per model*, and a 70B-class judge burns through that cap in a handful of
# eval runs. Pass --ragas-model to use a stronger, separately-quota'd judge
# (e.g. llama-3.3-70b-versatile) when more headroom is available.
DEFAULT_JUDGE_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
RAGAS_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def _relevant_pool(expected_substring, reranked_chunks, game_name):
    """Ground-truth relevant set for a case, built by scanning the live
    corpus rather than assuming a fixed relevant-doc count.

    Tries a few casing variants against Chroma's keyword search (its
    $contains match may be case-sensitive and we don't know the exact
    casing of the source PDF text), then filters everything through a
    case-insensitive Python check so the final set is always correct even
    if a variant over- or under-matches. The current top-k is unioned in
    too, so a chunk the pipeline actually retrieved can never be dropped
    from "relevant" just because the corpus scan missed it.
    """
    substring_lower = expected_substring.lower()
    variants = {expected_substring, expected_substring.lower(), expected_substring.title()}

    found = set()
    for variant in variants:
        for chunk in keyword_query(variant, n_results=100, game_name=game_name):
            if substring_lower in chunk.lower():
                found.add(chunk)

    found |= {chunk for chunk in reranked_chunks if substring_lower in chunk.lower()}
    return found


class Command(BaseCommand):
    help = (
        "Run the RAG eval suite end-to-end: retrieval metrics (Hit Rate, "
        "Recall@k, Precision@k, MRR@k) plus RAGAS generation metrics "
        "(faithfulness, answer relevancy, context precision, context recall)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--k", type=int, default=DEFAULT_K,
            help=f"top-k cutoff for retrieval metrics (default: {DEFAULT_K}, matches production)",
        )
        parser.add_argument(
            "--skip-ragas", action="store_true",
            help="only run retrieval metrics, skip the LLM-judged RAGAS metrics",
        )
        parser.add_argument(
            "--ragas-model", default=os.getenv("RAGAS_JUDGE_MODEL", DEFAULT_JUDGE_MODEL),
            help=f"Groq model used as the RAGAS judge (default: {DEFAULT_JUDGE_MODEL})",
        )
        parser.add_argument(
            "--json", dest="json_path", default=None,
            help="also write full per-case results to this JSON file",
        )

    def handle(self, *args, **options):
        k = options["k"]
        results = [self._run_case(case, k) for case in EVAL_CASES]

        self._print_case_table(results, k)
        self._print_retrieval_summary(results, k)

        if options["skip_ragas"]:
            self.stdout.write(self.style.WARNING("\nSkipped RAGAS metrics (--skip-ragas).\n"))
        else:
            self._run_ragas(results, options["ragas_model"])

        if options["json_path"]:
            with open(options["json_path"], "w") as f:
                json.dump(
                    [{k: v for k, v in r.items() if k != "reranked"} for r in results],
                    f, indent=2,
                )
            self.stdout.write(f"\nWrote full results to {options['json_path']}")

    # ---------------------------------------------------------------- run

    def _run_case(self, case, k):
        question = case["question"]

        candidates, detected_game = retrieve_candidates(question)
        reranked = rerank(question, candidates, top_k=k)
        context = build_context(reranked)
        answer = generate_answer(question, context)

        substring_lower = case["expected_substring"].lower()
        relevant = _relevant_pool(case["expected_substring"], reranked, detected_game)

        retrieved_hits = [chunk for chunk in reranked if chunk in relevant]
        true_positives = len(retrieved_hits)

        rank = next(
            (i for i, chunk in enumerate(reranked, 1) if substring_lower in chunk.lower()),
            None,
        )

        return {
            **case,
            "detected_game": detected_game,
            "num_candidates": len(candidates),
            "reranked": reranked,
            "context": context,
            "answer": answer,
            "relevant_pool_size": len(relevant),
            "rank": rank,
            "hit": rank is not None,
            "recall_at_k": (true_positives / len(relevant)) if relevant else 0.0,
            "precision_at_k": (true_positives / len(reranked)) if reranked else 0.0,
            "mrr_at_k": (1.0 / rank) if rank else 0.0,
        }

    # ------------------------------------------------------------- print

    def _print_case_table(self, results, k):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\nRetrieval metrics per case (k={k})\n"))
        header = f"{'case':<32} {'hit':<5} {'rank':<5} {'recall@k':<9} {'prec@k':<8} {'mrr@k':<7} {'|rel|':<5} game"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for r in results:
            status_text = ("HIT" if r["hit"] else "MISS").ljust(5)
            status = self.style.SUCCESS(status_text) if r["hit"] else self.style.ERROR(status_text)
            self.stdout.write(
                f"{r['label']:<32} {status} {r['rank'] or '-':<5} "
                f"{r['recall_at_k']:<9.2f} {r['precision_at_k']:<8.2f} {r['mrr_at_k']:<7.2f} "
                f"{r['relevant_pool_size']:<5} {r['detected_game'] or '-'}"
            )

    def _print_retrieval_summary(self, results, k):
        n = len(results)
        hit_rate = sum(r["hit"] for r in results) / n
        avg_recall = sum(r["recall_at_k"] for r in results) / n
        avg_precision = sum(r["precision_at_k"] for r in results) / n
        avg_mrr = sum(r["mrr_at_k"] for r in results) / n

        self.stdout.write(self.style.MIGRATE_HEADING("\nRetrieval summary\n"))
        self.stdout.write(f"  Hit Rate            : {sum(r['hit'] for r in results)}/{n} ({hit_rate * 100:.0f}%)")
        self.stdout.write(f"  Recall@{k:<3}         : {avg_recall:.3f}")
        self.stdout.write(f"  Precision@{k:<3}      : {avg_precision:.3f}")
        self.stdout.write(f"  MRR@{k:<3}            : {avg_mrr:.3f}")
        self.stdout.write(
            "\n  Note: Recall@k == Hit Rate whenever a case's relevant pool has exactly\n"
            "  one member. |rel| in the table above shows the actual ground-truth pool\n"
            "  size found by scanning the live corpus for the expected substring, so\n"
            "  Recall/Precision only diverge from Hit Rate on cases where |rel| > 1.\n"
        )

    # ------------------------------------------------------------- ragas

    def _run_ragas(self, results, judge_model):
        self.stdout.write(self.style.MIGRATE_HEADING("RAGAS metrics (LLM-judged generation quality)\n"))
        try:
            from ragas import EvaluationDataset, evaluate
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from ragas.llms import LangchainLLMWrapper
            from ragas.metrics import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness
            from langchain_openai import ChatOpenAI
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError as exc:
            self.stdout.write(self.style.ERROR(
                f"RAGAS metrics need extra packages that aren't installed yet ({exc}).\n"
                "Install them with:\n\n"
                "  pip install ragas langchain-openai langchain-huggingface datasets\n\n"
                "or re-run with --skip-ragas to see retrieval metrics only."
            ))
            return

        # Groq's API is OpenAI-compatible, so the judge LLM goes through
        # ChatOpenAI pointed at Groq's endpoint rather than langchain-groq -
        # langchain-groq pins groq<1.0, which conflicts with (and silently
        # downgrades) the groq==1.0.0 the production chat service depends on.
        #
        # bypass_n=True stops ragas from requesting multiple sampled
        # completions per call (n>1) for self-consistency - Groq's API
        # rejects n>1 outright ("number must be at most 1"), which without
        # this surfaces as silent nan scores and cascading timeouts.
        judge_llm = LangchainLLMWrapper(
            ChatOpenAI(
                model=judge_model,
                api_key=os.getenv("GROQ_API_KEY"),
                base_url="https://api.groq.com/openai/v1",
            ),
            bypass_n=True,
        )
        judge_embeddings = LangchainEmbeddingsWrapper(HuggingFaceEmbeddings(model_name=RAGAS_EMBEDDING_MODEL))

        dataset = EvaluationDataset.from_list([
            {
                "user_input": r["question"],
                "response": r["answer"],
                "retrieved_contexts": r["reranked"] or [""],
                "reference": r["reference"],
            }
            for r in results
        ])

        try:
            outcome = evaluate(
                dataset=dataset,
                metrics=[Faithfulness(), AnswerRelevancy(), ContextPrecision(), ContextRecall()],
                llm=judge_llm,
                embeddings=judge_embeddings,
            )
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"RAGAS evaluation failed: {exc!r}"))
            return

        df = outcome.to_pandas()
        metric_cols = [c for c in ("faithfulness", "answer_relevancy", "context_precision", "context_recall") if c in df.columns]

        header = f"{'case':<32} " + " ".join(f"{c:<18}" for c in metric_cols)
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for i, row in df.iterrows():
            label = results[i]["label"] if i < len(results) else str(i)
            self.stdout.write(f"{label:<32} " + " ".join(f"{row[c]:<18.2f}" for c in metric_cols))

        self.stdout.write(self.style.MIGRATE_HEADING("\nRAGAS averages\n"))
        for c in metric_cols:
            self.stdout.write(f"  {c:<18}: {df[c].mean():.3f}")
