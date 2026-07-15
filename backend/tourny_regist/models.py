from django.conf import settings
from django.db import models


class Tournament(models.Model):
    name = models.CharField(max_length=200)
    game = models.ForeignKey('games.Game', related_name='tournaments', on_delete=models.CASCADE)
    organizer = models.ForeignKey('organizer.Organizer', related_name='tournaments', on_delete=models.CASCADE)
    starts_at = models.DateTimeField()
    max_participants = models.PositiveIntegerField(null=True, blank=True)
    is_registration_open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Registration(models.Model):
    tournament = models.ForeignKey(Tournament, related_name='registrations', on_delete=models.CASCADE)
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='tournament_registrations', on_delete=models.CASCADE,
    )
    registered_at = models.DateTimeField(auto_now_add=True)
    checked_in = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tournament', 'player'], name='unique_tournament_registration'),
        ]
        ordering = ['-registered_at']

    def __str__(self):
        return f'{self.player_id} -> {self.tournament_id}'
