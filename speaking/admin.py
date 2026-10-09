from django.contrib import admin

from .models import SpeakingEvaluation, SpeakingSubmission


@admin.register(SpeakingSubmission)
class SpeakingSubmissionAdmin(admin.ModelAdmin):
    list_display = ("student", "question", "processing_status", "score", "submitted_at")
    list_filter = ("processing_status",)
    search_fields = ("student__email", "student__first_name", "student__last_name")
    readonly_fields = [f.name for f in SpeakingSubmission._meta.fields]


@admin.register(SpeakingEvaluation)
class SpeakingEvaluationAdmin(admin.ModelAdmin):
    list_display = ("submission", "overall_score", "pronunciation_assessed", "provider", "created_at")
    readonly_fields = [f.name for f in SpeakingEvaluation._meta.fields]
