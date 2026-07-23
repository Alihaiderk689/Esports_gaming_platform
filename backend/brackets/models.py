from django.conf import settings
from django.db import models

from tourny_regist.models import Tournament


class Bracket(models.Model):
    class Format(models.TextChoices):
        SINGLE = 'single', 'Single Elimination'
        DOUBLE = 'double', 'Double Elimination'
        GUARANTEE3 = 'guarantee3', '3-Game Guarantee'
        ROUND_ROBIN = 'round_robin', 'Round Robin'
        SWISS = 'swiss', 'Swiss System'
        GROUP_PLAYOFF = 'group_playoff', 'Group Stage + Playoff'

    tournament = models.OneToOneField(Tournament, related_name='bracket', on_delete=models.CASCADE)
    format = models.CharField(max_length=20, choices=Format.choices, default=Format.SINGLE)
    total_rounds = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Bracket for {self.tournament_id}'


class Match(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        READY = 'ready', 'Ready'
        COMPLETED = 'completed', 'Completed'

    class Side(models.TextChoices):
        WINNERS = 'winners', 'Winners'
        LOSERS = 'losers', 'Losers'
        GRAND_FINAL = 'grand_final', 'Grand Final'
        GUARANTEE = 'guarantee', 'Guarantee'
        GROUP = 'group', 'Group'

    bracket = models.ForeignKey(Bracket, related_name='matches', on_delete=models.CASCADE)
    tournament = models.ForeignKey(Tournament, related_name='matches', on_delete=models.CASCADE)
    bracket_side = models.CharField(max_length=15, choices=Side.choices, default=Side.WINNERS)
    group_label = models.CharField(max_length=5, null=True, blank=True)
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

    loser_next_match = models.ForeignKey(
        'self', related_name='previous_matches_as_loser', null=True, blank=True, on_delete=models.SET_NULL,
    )
    loser_next_match_slot = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=[(1, 'Player 1'), (2, 'Player 2')],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['bracket', 'bracket_side', 'round_number', 'position'], name='unique_match_slot',
            ),
        ]
        ordering = ['bracket_side', 'round_number', 'position']

    def __str__(self):
        return f'{self.bracket_side} round {self.round_number} #{self.position} ({self.tournament_id})'
