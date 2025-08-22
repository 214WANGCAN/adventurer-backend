from django.contrib import admin
from .models import Task

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'title', 'task_type', 'publisher', 'deadline',
        'experience_reward', 'token_reward',
        'is_completed', 'is_expired', 'created_at'
    )
    list_filter = ('task_type', 'is_completed', 'is_expired', 'deadline')
    search_fields = ('title', 'description', 'publisher__username')
    readonly_fields = ('created_at', 'updated_at')

    filter_horizontal = ('accepted_by',)
    autocomplete_fields = ['publisher', 'leader']
