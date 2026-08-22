import logging

from django.db import transaction
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import APIException


from rag_chat.models import (
    RuleBook,
    ChatHistory
)


from rag_chat.serializers import (
    RuleBookSerializer,
    RuleBookUploadSerializer,
    ChatRequestSerializer,
    ChatHistorySerializer,
)


from games.models import Game
from rag_chat.services.cloudinary_service import delete_pdf, upload_pdf
from rag_chat.services.pdf_service import extract_text_from_pdf
from rag_chat.services.chunk_service import split_text_into_chunks
from rag_chat.services.embedding_service import generate_embeddings
from rag_chat.services.chroma_service import add_chunks, delete_rulebook
from rag_chat.services.game_detector import detect_games
from rag_chat.services.retrieval_service import retrieve_candidates
from rag_chat.services.rerank_service import rerank
from rag_chat.services.prompt_service import build_context
from rag_chat.services.groq_service import GUARDRAIL_MESSAGE, generate_answer

logger = logging.getLogger(__name__)

_HISTORY_TURNS = 3


def _ambiguous_game_clarification():
    """Asked instead of running retrieval when neither the current question
    nor the conversation history names a game at all - see
    docs/EDGE_CASES.md's "ambiguous RAG question" entry. Guessing here risks
    a vector/keyword match landing on the wrong game's rulebook and
    confidently answering from it, which is worse than declining."""
    examples = list(Game.objects.order_by('name').values_list('name', flat=True)[:5])
    if examples:
        return (
            "I couldn't tell which game your question is about, and guessing could mean "
            f"answering from the wrong game's rulebook. Could you name the game — for example: "
            f"{', '.join(examples)}?"
        )
    return "I couldn't tell which game your question is about. Could you name the game you're asking about?"


class ChatServiceUnavailable(APIException):

    status_code = 503

    default_detail = (
        "The chat assistant is temporarily unavailable. Please try again."
    )

    default_code = "service_unavailable"


class RuleBookProcessingError(APIException):

    status_code = 503

    default_detail = (
        "Could not process this rulebook right now. Please try again."
    )

    default_code = "service_unavailable"



# ==========================
# RuleBook APIs
# ==========================


class RuleBookListView(generics.ListAPIView):

    queryset = RuleBook.objects.all()

    serializer_class = RuleBookSerializer

    permission_classes = [
        permissions.IsAuthenticated
    ]



class RuleBookUploadView(generics.CreateAPIView):

    serializer_class = RuleBookUploadSerializer

    permission_classes = [
        permissions.IsAdminUser
    ]


    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(
            data=request.data
        )


        serializer.is_valid(
            raise_exception=True
        )


        pdf_file = serializer.validated_data.pop(
            "pdf"
        )

        try:
            cloudinary_data = upload_pdf(pdf_file)
        except Exception:
            logger.exception("Failed to upload rulebook PDF to Cloudinary")
            raise RuleBookProcessingError("Could not upload the PDF. Please try again.")

        try:
            with transaction.atomic():
                rulebook = RuleBook.objects.create(
                    **serializer.validated_data,
                    pdf_url=cloudinary_data["url"],
                    public_id=cloudinary_data["public_id"],
                    uploaded_by=request.user,
                )

                pdf_file.seek(0)
                pdf_content = pdf_file.read()
                text = extract_text_from_pdf(pdf_content)
                chunks = split_text_into_chunks(text)
                embeddings = generate_embeddings([chunk["text"] for chunk in chunks])
                add_chunks(rulebook.id, chunks, embeddings)

                rulebook.is_processed = True
                rulebook.save(update_fields=["is_processed"])
        except Exception:
            # transaction.atomic() already rolled back the RuleBook row — the
            # Cloudinary asset is the one thing left over from before the
            # rollback boundary, so it needs its own best-effort cleanup here.
            logger.exception(
                "Failed to process rulebook PDF (public_id=%s)", cloudinary_data.get("public_id"),
            )
            try:
                delete_pdf(cloudinary_data["public_id"])
            except Exception:
                logger.exception(
                    "Failed to clean up Cloudinary asset %s after a processing failure",
                    cloudinary_data.get("public_id"),
                )
            raise RuleBookProcessingError("The PDF was uploaded but could not be processed. Please try again.")

        return Response(

            RuleBookSerializer(rulebook).data,

            status=status.HTTP_201_CREATED

        )



class RuleBookDeleteView(generics.DestroyAPIView):

    queryset = RuleBook.objects.all()

    permission_classes = [
        permissions.IsAdminUser
    ]

    def perform_destroy(self, instance):
        delete_rulebook(instance.id)
        delete_pdf(instance.public_id)
        super().perform_destroy(instance)



# ==========================
# Chat API
# ==========================


class ChatView(APIView):

    permission_classes = [
        permissions.IsAuthenticated
    ]
    throttle_scope = 'chat'


    def post(self, request):

        serializer = ChatRequestSerializer(
            data=request.data
        )


        serializer.is_valid(
            raise_exception=True
        )


        question = serializer.validated_data["message"]

        recent_history = list(
            ChatHistory.objects.filter(user=request.user).order_by("-created_at")[:_HISTORY_TURNS]
        )
        recent_history.reverse()
        history_payload = [{"question": h.question, "answer": h.answer} for h in recent_history]

        previous_game = recent_history[-1].game_name if recent_history else None

        if not detect_games(question) and not previous_game:
            # Neither this question nor the conversation so far names a game -
            # an unscoped search here risks landing on the wrong game's
            # rulebook and confidently answering from it. Ask instead of
            # guessing; this never touches embeddings/Chroma/Groq, so an
            # ambiguous question costs nothing beyond a cheap regex scan, and
            # deliberately isn't saved as ChatHistory - there's no game
            # context or grounded answer here for a later turn to fall back
            # on.
            return Response(
                {'question': question, 'answer': _ambiguous_game_clarification(), 'game_name': ''},
                status=status.HTTP_200_OK,
            )

        try:

            candidate_chunks, detected_game = retrieve_candidates(question, fallback_game=previous_game)
            retrieved_chunks = rerank(question, candidate_chunks, top_k=12)
            context = build_context(retrieved_chunks)

            answer = generate_answer(question, context, history=history_payload)

            logger.info(
                "rag_chat question=%r game=%r candidates=%d used=%d guardrail=%s",
                question, detected_game, len(candidate_chunks), len(retrieved_chunks),
                answer.strip() == GUARDRAIL_MESSAGE,
            )


        except Exception:

            logger.exception("rag_chat pipeline failed for question=%r", question)
            raise ChatServiceUnavailable()



        chat = ChatHistory.objects.create(

            user=request.user,

            question=question,

            answer=answer,

            game_name=detected_game or "",

        )



        return Response(

            ChatHistorySerializer(chat).data,

            status=status.HTTP_201_CREATED

        )



# ==========================
# Chat History
# ==========================


class ChatHistoryView(generics.ListAPIView):

    serializer_class = ChatHistorySerializer

    permission_classes = [
        permissions.IsAuthenticated
    ]


    def get_queryset(self):

        return ChatHistory.objects.filter(
            user=self.request.user
        )
