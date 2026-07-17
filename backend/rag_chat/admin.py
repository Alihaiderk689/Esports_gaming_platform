from django.contrib import admin

from .models import RuleBook, ChatHistory


@admin.register(RuleBook)
class RuleBookAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "game",
        "is_processed",
        "uploaded_at"
    )


@admin.register(ChatHistory)
class ChatHistoryAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "question",
        "created_at"
    )