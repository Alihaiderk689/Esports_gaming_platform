from django.conf import settings
from django.db import models

from tourny_regist.models import Tournament


class Bracket(models.Model):
    tournament = models.OneToOneField(Tournament, related_name='bracket', on_delete=models.CASCADE)
    total_rounds = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Bracket for {self.tournament_id}'


class Match(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        READY = 'ready', 'Ready'
        COMPLETED = 'completed', 'Completed'

    bracket = models.ForeignKey(Bracket, related_name='matches', on_delete=models.CASCADE)
    tournament = models.ForeignKey(Tournament, related_name='matches', on_delete=models.CASCADE)
    round_number = models.PositiveIntegerField()
    position = models.PositiveIntegerField()

    player1 = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='matches_as_player1',
        null=True, blank=True, on_delete=models.SET_NULL,
    )
    player2 = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='matches_as_player2',
        null=True, blank=True, on_delete=models.SET_NULL,
    )
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='matches_won',
        null=True, blank=True, on_delete=models.SET_NULL,
    )
    score = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    next_match = models.ForeignKey(
        'self', related_name='previous_matches', null=True, blank=True, on_delete=models.SET_NULL,
    )
    next_match_slot = models.PositiveSmallIntegerField(null=True, blank=True, choices=[(1, 'Player 1'), (2, 'Player 2')])

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['bracket', 'round_number', 'position'], name='unique_match_slot'),
        ]
        ordering = ['round_number', 'position']

    def __str__(self):
        return f'Round {self.round_number} #{self.position} ({self.tournament_id})'
