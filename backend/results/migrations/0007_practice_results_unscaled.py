from django.db import migrations


def forwards(apps, schema_editor):
    """Part practice of Reading/Listening no longer gets a 0–75 score or CEFR level."""
    Result = apps.get_model("results", "Result")
    rows = Result.objects.filter(attempt__practice__gt="", attempt__exam__section__in=["reading", "listening"])
    for r in rows.select_related("attempt"):
        a = r.attempt
        total = (a.correct_count or 0) + (a.incorrect_count or 0) + (a.unanswered_count or 0)
        r.scaled_score = None
        r.cefr_level = ""
        r.feedback = (f"Part practice: {a.correct_count or 0} of {total} correct ({float(a.percentage or 0):.0f}%). "
                      "Take the full test to get a Multilevel score (0–75) and CEFR level.")
        r.save(update_fields=["scaled_score", "cefr_level", "feedback"])


class Migration(migrations.Migration):
    dependencies = [("results", "0006_examattempt_drafts_examattempt_drafts_saved_at")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
