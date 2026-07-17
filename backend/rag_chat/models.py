from django.db import models
from django.conf import settings

from games.models import Game


class RuleBook(models.Model):

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="rulebooks"
    )

    title = models.CharField(
        max_length=255
    )

    pdf_url = models.URLField()

    public_id = models.CharField(
        max_length=255,
        unique=True
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_rulebooks"
    )

    is_processed = models.BooleanField(
        default=False
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):
        return self.title



class ChatHistory(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_history"
    )

    document = models.ForeignKey(
        RuleBook,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chats"
    )

    question = models.TextField()

    answer = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):
        return f"{self.user} - {self.question[:30]}"