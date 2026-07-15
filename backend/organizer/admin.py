from django.contrib import admin

from organizer.models import Organizer


@admin.register(Organizer)
class OrganizerAdmin(admin.ModelAdmin):
    list_display = ['company_name', 'user', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['company_name', 'user__email', 'cnic_number', 'company_registration_number']
    actions = ['approve_organizers', 'reject_organizers']

    @admin.action(description='Approve selected organizers')
    def approve_organizers(self, request, queryset):
        queryset.update(status=Organizer.Status.APPROVED, rejection_reason='')

    @admin.action(description='Reject selected organizers')
    def reject_organizers(self, request, queryset):
        queryset.update(status=Organizer.Status.REJECTED)
