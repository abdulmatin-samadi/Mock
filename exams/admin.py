from django.contrib import admin

from .models import ExamPart, MockExam, Option, Question, SpeakingQuestion, WritingTask


class OptionInline(admin.TabularInline):
    model = Option
    extra = 0


@admin.register(MockExam)
class MockExamAdmin(admin.ModelAdmin):
    list_display = ("title", "section", "level", "is_published", "created_at")
    list_filter = ("section", "level", "is_published")
    search_fields = ("title",)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("order", "prompt", "question_type", "exam", "points")
    list_filter = ("question_type",)
    inlines = [OptionInline]


admin.site.register(ExamPart)
admin.site.register(WritingTask)
admin.site.register(SpeakingQuestion)
