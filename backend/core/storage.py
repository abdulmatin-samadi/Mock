"""Storage helpers.

Model fields reference these callables (not storage instances) so the
backend can change via settings.STORAGES (e.g. local disk -> S3) without
new migrations.
"""
import os
import uuid

from django.core.files.storage import storages
from django.utils import timezone


def private_storage():
    return storages["private"]


def random_upload_path(prefix):
    """Return an upload_to callable that stores files under
    <prefix>/<YYYY>/<MM>/<uuid>.<ext> — never trusting the client filename."""

    def _upload_to(instance, filename):
        ext = os.path.splitext(filename)[1].lower()[:10]
        now = timezone.now()
        return f"{prefix}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{ext}"

    _upload_to.__name__ = f"upload_to_{prefix.replace('/', '_')}"
    return _upload_to


# Named, importable upload_to callables (required for migrations serialisation).
def avatar_path(instance, filename):
    return random_upload_path("avatars")(instance, filename)


def course_thumbnail_path(instance, filename):
    return random_upload_path("courses/thumbnails")(instance, filename)


def lesson_video_path(instance, filename):
    return random_upload_path("courses/videos")(instance, filename)


def lesson_material_path(instance, filename):
    return random_upload_path("courses/materials")(instance, filename)


def listening_audio_path(instance, filename):
    return random_upload_path("exams/listening")(instance, filename)


def writing_image_path(instance, filename):
    return random_upload_path("exams/writing")(instance, filename)


def speaking_recording_path(instance, filename):
    return random_upload_path("speaking/recordings")(instance, filename)
