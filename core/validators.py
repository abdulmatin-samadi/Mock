"""Upload validation: extension allow-list, size limit and content sniffing
(magic bytes / Pillow). A file must pass all three checks."""
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models.fields.files import FieldFile
from django.utils.deconstruct import deconstructible


def _head(file, n=64):
    pos = file.tell() if hasattr(file, "tell") else 0
    try:
        file.seek(0)
        data = file.read(n)
    finally:
        try:
            file.seek(pos)
        except Exception:
            pass
    return data or b""


def _is_webm(h):
    return h.startswith(b"\x1a\x45\xdf\xa3")


def _is_ogg(h):
    return h.startswith(b"OggS")


def _is_wav(h):
    return h[:4] == b"RIFF" and h[8:12] == b"WAVE"


def _is_mp3(h):
    return h.startswith(b"ID3") or (len(h) > 1 and h[0] == 0xFF and (h[1] & 0xE0) == 0xE0)


def _is_iso_media(h):  # mp4 / m4a / mov
    return h[4:8] == b"ftyp"


def _is_pdf(h):
    return h.startswith(b"%PDF-")


def _is_zip_office(h):  # docx / pptx / xlsx are zip containers
    return h.startswith(b"PK\x03\x04")


KINDS = {
    "image": {
        "extensions": {".jpg", ".jpeg", ".png", ".webp", ".gif"},
        "sniffers": None,  # verified with Pillow instead
    },
    "document": {
        "extensions": {".pdf", ".docx", ".pptx", ".xlsx", ".txt"},
        "sniffers": {".pdf": _is_pdf, ".docx": _is_zip_office, ".pptx": _is_zip_office,
                     ".xlsx": _is_zip_office, ".txt": None},
    },
    "video": {
        "extensions": {".mp4", ".webm", ".mov", ".m4v"},
        "sniffers": {".mp4": _is_iso_media, ".m4v": _is_iso_media, ".mov": _is_iso_media, ".webm": _is_webm},
    },
    "audio": {
        "extensions": {".mp3", ".wav", ".ogg", ".oga", ".m4a", ".webm", ".mp4"},
        "sniffers": {".mp3": _is_mp3, ".wav": _is_wav, ".ogg": _is_ogg, ".oga": _is_ogg,
                     ".m4a": _is_iso_media, ".mp4": _is_iso_media, ".webm": _is_webm},
    },
}
# Speaking recordings share the audio rules but have their own size limit.
KINDS["recording"] = KINDS["audio"]


@deconstructible
class FileValidator:
    """Validate an uploaded file of a given kind (image/document/video/audio/recording)."""

    def __init__(self, kind):
        if kind not in KINDS:
            raise ValueError(f"Unknown file kind: {kind}")
        self.kind = kind

    def __eq__(self, other):
        return isinstance(other, FileValidator) and other.kind == self.kind

    def __call__(self, file):
        # Files already in storage were validated when they were uploaded.
        if isinstance(file, FieldFile) and getattr(file, "_committed", True):
            return
        rules = KINDS[self.kind]
        name = getattr(file, "name", "") or ""
        ext = os.path.splitext(name)[1].lower()
        if ext not in rules["extensions"]:
            allowed = ", ".join(sorted(rules["extensions"]))
            raise ValidationError(f"Unsupported file type '{ext or '?'}'. Allowed: {allowed}.")

        limit_mb = settings.UPLOAD_LIMITS_MB[self.kind]
        size = getattr(file, "size", None)
        if size is not None and size > limit_mb * 1024 * 1024:
            raise ValidationError(f"File too large. Maximum size is {limit_mb} MB.")
        if size == 0:
            raise ValidationError("The file is empty.")

        if self.kind == "image":
            self._validate_image(file)
            return
        sniffer = rules["sniffers"].get(ext)
        if sniffer is not None and not sniffer(_head(file)):
            raise ValidationError("File content does not match its extension.")
        if ext == ".txt":
            try:
                _head(file, 4096).decode("utf-8")
            except UnicodeDecodeError:
                raise ValidationError("Text files must be UTF-8.")

    @staticmethod
    def _validate_image(file):
        from PIL import Image

        pos = file.tell()
        try:
            file.seek(0)
            img = Image.open(file)
            img.verify()
            if img.format not in {"JPEG", "PNG", "WEBP", "GIF"}:
                raise ValidationError("Unsupported image format.")
            if img.width * img.height > 40_000_000:
                raise ValidationError("Image dimensions are too large.")
        except ValidationError:
            raise
        except Exception:
            raise ValidationError("Upload a valid image.")
        finally:
            file.seek(pos)


validate_image = FileValidator("image")
validate_document = FileValidator("document")
validate_video = FileValidator("video")
validate_audio = FileValidator("audio")
validate_recording = FileValidator("recording")


AUDIO_CONTENT_TYPES = {
    ".webm": "audio/webm", ".ogg": "audio/ogg", ".oga": "audio/ogg", ".mp3": "audio/mpeg",
    ".wav": "audio/wav", ".m4a": "audio/mp4", ".mp4": "audio/mp4",
}
