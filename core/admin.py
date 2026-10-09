from django.contrib import admin

from .models import Word


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ("word", "part_of_speech", "level", "is_active")
    list_filter = ("level", "is_active")
    search_fields = ("word", "definition")
