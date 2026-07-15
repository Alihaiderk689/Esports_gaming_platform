from django.contrib import admin

from rag_chat.models import ChatMessage, Rule


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ['title', 'uploaded_by', 'created_at']
    search_fields = ['title', 'content']


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'created_at']
    list_filter = ['role']
    search_fields = ['user__email', 'content']
