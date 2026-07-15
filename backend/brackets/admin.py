from django.contrib import admin

from brackets.models import Bracket, Match


@admin.register(Bracket)
class BracketAdmin(admin.ModelAdmin):
    list_display = ['tournament', 'total_rounds', 'created_at']


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ['tournament', 'round_number', 'position', 'player1', 'player2', 'winner', 'status']
    list_filter = ['status', 'round_number']
    search_fields = ['tournament__name', 'player1__email', 'player2__email']
