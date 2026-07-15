from django.contrib import admin

from tourny_regist.models import Registration, Tournament


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ['name', 'game', 'organizer', 'starts_at', 'max_participants', 'is_registration_open']
    list_filter = ['is_registration_open', 'game']
    search_fields = ['name', 'organizer__company_name']


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ['tournament', 'player', 'registered_at', 'checked_in']
    list_filter = ['checked_in']
    search_fields = ['tournament__name', 'player__email']
