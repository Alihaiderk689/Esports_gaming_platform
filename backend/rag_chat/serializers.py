from rest_framework import serializers

from rag_chat.models import ChatMessage, Rule


class RuleSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.EmailField(source='uploaded_by.email', read_only=True)

    class Meta:
        model = Rule
        fields = ['id', 'title', 'content', 'uploaded_by', 'uploaded_by_email', 'created_at']
        read_only_fields = ['id', 'uploaded_by', 'uploaded_by_email', 'created_at']


class RuleUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rule
        fields = ['title', 'content']


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'created_at']
        read_only_fields = fields


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=4000)
