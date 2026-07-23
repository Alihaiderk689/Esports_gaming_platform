from django.contrib import admin

from games.models import Category, Game


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ['name', 'genre', 'platform', 'is_active', 'created_at']
    list_filter = ['genre', 'platform', 'is_active', 'categories']
    search_fields = ['name', 'genre', 'platform']
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ['categories']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    prepopulated_fields = {'slug': ('name',)}
