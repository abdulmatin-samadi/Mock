from django.contrib import admin

from .models import Answer, ExamAttempt, Result


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ("student", "exam", "status", "percentage", "started_at", "submitted_at")
    list_filter = ("status", "exam__section")
    search_fields = ("student__email", "student__first_name", "student__last_name", "exam__title")
    # Scores are computed by the server only — read-only even in Django admin.
    readonly_fields = [f.name for f in ExamAttempt._meta.fields]


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("attempt", "scaled_score", "cefr_level", "created_at")
    readonly_fields = [f.name for f in Result._meta.fields]


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "answer", "is_correct", "points")
    readonly_fields = [f.name for f in Answer._meta.fields]
