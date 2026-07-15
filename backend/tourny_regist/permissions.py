from rest_framework import permissions


class IsTournamentStaffOrAdmin(permissions.BasePermission):
    # Checked manually against a Tournament instance; views here operate on Registration querysets.
    def has_object_permission(self, request, view, tournament):
        if request.user.is_staff:
            return True
        organizer_profile = getattr(request.user, 'organizer_profile', None)
        return organizer_profile is not None and tournament.organizer_id == organizer_profile.pk
