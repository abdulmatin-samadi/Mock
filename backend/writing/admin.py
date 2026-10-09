from django.contrib import admin

from .models import WritingEvaluation, WritingSubmission


@admin.register(WritingSubmission)
class WritingSubmissionAdmin(admin.ModelAdmin):
    list_display = ("student", "task", "word_count", "score", "status", "submitted_at")
    list_filter = ("status",)
    search_fields = ("student__email", "student__first_name", "student__last_name")
    readonly_fields = [f.name for f in WritingSubmission._meta.fields]


@admin.register(WritingEvaluation)
class WritingEvaluationAdmin(admin.ModelAdmin):
    list_display = ("submission", "overall_score", "cefr_level", "provider", "model_name", "created_at")
    readonly_fields = [f.name for f in WritingEvaluation._meta.fields]
