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


from rag_chat.services.cloudinary_service import delete_pdf, upload_pdf
from rag_chat.services.pdf_service import extract_text_from_pdf
from rag_chat.services.chunk_service import split_text_into_chunks
from rag_chat.services.embedding_service import generate_embeddings
from rag_chat.services.chroma_service import add_chunks, delete_rulebook
from rag_chat.services.retrieval_service import retrieve_candidates
from rag_chat.services.rerank_service import rerank
from rag_chat.services.prompt_service import build_context
from rag_chat.services.groq_service import GUARDRAIL_MESSAGE, generate_answer

logger = logging.getLogger(__name__)

_HISTORY_TURNS = 3


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



        try:

            recent_history = list(
                ChatHistory.objects.filter(user=request.user).order_by("-created_at")[:_HISTORY_TURNS]
            )
            recent_history.reverse()
            history_payload = [{"question": h.question, "answer": h.answer} for h in recent_history]

            previous_game = recent_history[-1].game_name if recent_history else None

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
