from django.db import migrations

# The platform is Multilevel-only: map former IELTS / generic writing task types.
MAPPING = {"ielts_task1": "task1_2", "ielts_task2": "task2", "multilevel": "task2"}


def forwards(apps, schema_editor):
    WritingTask = apps.get_model("exams", "WritingTask")
    for old, new in MAPPING.items():
        WritingTask.objects.filter(task_type=old).update(task_type=new)


class Migration(migrations.Migration):
    dependencies = [("exams", "0002_remove_mockexam_exams_mocke_section_d0610c_idx_and_more")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
