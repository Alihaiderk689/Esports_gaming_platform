from rest_framework import serializers

from rag_chat.models import RuleBook, ChatHistory


# ==========================
# RuleBook Serializers
# ==========================


class RuleBookSerializer(serializers.ModelSerializer):

    class Meta:
        model = RuleBook

        fields = [
            "id",
            "game",
            "title",
            "pdf_url",
            "public_id",
            "uploaded_by",
            "is_processed",
            "uploaded_at",
        ]

        read_only_fields = [
            "uploaded_by",
            "is_processed",
            "uploaded_at",
        ]


class RuleBookUploadSerializer(serializers.ModelSerializer):

    pdf = serializers.FileField(
        write_only=True
    )

    class Meta:
        model = RuleBook

        fields = [
            "game",
            "title",
            "pdf",
        ]


# ==========================
# Chat Serializers
# ==========================


class ChatRequestSerializer(serializers.Serializer):

    message = serializers.CharField(
        required=True,
        allow_blank=False
    )


class ChatHistorySerializer(serializers.ModelSerializer):

    class Meta:
        model = ChatHistory

        fields = [
            "id",
            "user",
            "document",
            "question",
            "answer",
            "created_at",
        ]

        read_only_fields = [
            "user",
            "created_at",
        ]