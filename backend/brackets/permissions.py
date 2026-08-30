from rest_framework import permissions

from tourny_regist.models import Registration, TeamMembership, Tournament


class IsPublicOrTournamentStakeholder(permissions.BasePermission):
    """Bracket/match viewing: open to any authenticated user once the
    tournament is public (approved + published); before that, restricted to
    staff, the organizer, or one of the tournament's own registered players/
    team members. Mirrors tourny_regist.permissions.IsPublicOrOwner's shape,
    extended with the "registered participant" case since a bracket has
    stakeholders (players) that a bare tournament-visibility check doesn't."""

    def has_object_permission(self, request, view, tournament):
        if tournament.status == Tournament.Status.APPROVED and tournament.is_published:
            return True
        if request.user.is_staff:
            return True
        organizer_profile = getattr(request.user, 'organizer_profile', None)
        if organizer_profile is not None and tournament.organizer_id == organizer_profile.pk:
            return True
        if Registration.objects.filter(tournament=tournament, player=request.user).exists():
            return True
        return TeamMembership.objects.filter(player=request.user, team__tournament=tournament).exists()
