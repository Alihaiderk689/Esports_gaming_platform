from django.contrib import admin

from games.models import Game


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ['name', 'genre', 'platform', 'is_active', 'created_at']
    list_filter = ['genre', 'platform', 'is_active']
    search_fields = ['name', 'genre', 'platform']
    prepopulated_fields = {'slug': ('name',)}
