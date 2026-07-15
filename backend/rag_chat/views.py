import anthropic
from rest_framework import generics, permissions, status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from rag_chat.models import ChatMessage, Rule
from rag_chat.serializers import (
    ChatMessageSerializer,
    ChatRequestSerializer,
    RuleSerializer,
    RuleUploadSerializer,
)
from rag_chat.services import ChatNotConfigured, get_chat_response


class ChatServiceUnavailable(APIException):
    status_code = 503
    default_detail = 'The chat assistant is temporarily unavailable. Please try again.'
    default_code = 'service_unavailable'


class RuleListView(generics.ListAPIView):
    queryset = Rule.objects.all()
    serializer_class = RuleSerializer
    permission_classes = [permissions.IsAuthenticated]


class RuleUploadView(generics.CreateAPIView):
    serializer_class = RuleUploadSerializer
    permission_classes = [permissions.IsAdminUser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = serializer.save(uploaded_by=request.user)
        return Response(RuleSerializer(rule).data, status=status.HTTP_201_CREATED)


class RuleDeleteView(generics.DestroyAPIView):
    queryset = Rule.objects.all()
    permission_classes = [permissions.IsAdminUser]


class ChatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message_text = serializer.validated_data['message']

        ChatMessage.objects.create(user=request.user, role=ChatMessage.Role.USER, content=message_text)

        try:
            reply_text, _ = get_chat_response(request.user, message_text)
        except (ChatNotConfigured, anthropic.AuthenticationError):
            raise ChatServiceUnavailable('Chat assistant is not configured correctly.')
        except (anthropic.APIConnectionError, anthropic.APIStatusError):
            raise ChatServiceUnavailable()

        assistant_message = ChatMessage.objects.create(
            user=request.user, role=ChatMessage.Role.ASSISTANT, content=reply_text,
        )
        return Response(ChatMessageSerializer(assistant_message).data, status=status.HTTP_201_CREATED)


class ChatHistoryView(generics.ListAPIView):
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatMessage.objects.filter(user=self.request.user)
