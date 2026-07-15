from django.conf import settings
from django.db import models


class Rule(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='uploaded_rules', on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = 'user', 'User'
        ASSISTANT = 'assistant', 'Assistant'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='chat_messages', on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.role}: {self.content[:50]}'
