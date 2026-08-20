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
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        # created_by is nullable (SET_NULL — see Tournament.created_by's
        # docstring) so it survives the creator's account being deleted.
        # Without the is_authenticated guard above, an anonymous request's
        # `request.user.pk` is also None, and `None == None` would
        # incorrectly grant "owner" access to *any* unpublished tournament
        # whose creator's account happens to have been deleted.
        return tournament.created_by_id == request.user.pk


class IsApprovedOrganizer(permissions.BasePermission):
    message = 'You must be an approved organizer to create a tournament.'

    def has_permission(self, request, view):
        organizer_profile = getattr(request.user, 'organizer_profile', None)
        return organizer_profile is not None and organizer_profile.status == Organizer.Status.APPROVED
