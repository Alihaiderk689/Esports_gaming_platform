from rest_framework import permissions

from organizer.models import Organizer
from tourny_regist.models import Tournament


class IsTournamentStaffOrAdmin(permissions.BasePermission):
    # Checked manually against a Tournament instance; views here operate on Registration querysets.
    def has_object_permission(self, request, view, tournament):
        if request.user.is_staff:
            return True
        organizer_profile = getattr(request.user, 'organizer_profile', None)
        return organizer_profile is not None and tournament.organizer_id == organizer_profile.pk


class IsPublicOrOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, tournament):
        if tournament.status == Tournament.Status.APPROVED and tournament.is_published:
            return True
        if request.user.is_staff:
            return True
        return tournament.created_by_id == request.user.pk


class IsApprovedOrganizer(permissions.BasePermission):
    message = 'You must be an approved organizer to create a tournament.'

    def has_permission(self, request, view):
        organizer_profile = getattr(request.user, 'organizer_profile', None)
        return organizer_profile is not None and organizer_profile.status == Organizer.Status.APPROVED
