"""Streaming of private files through permission-checked views.

Supports HTTP Range requests so <audio>/<video> seeking works (Safari requires it).
In production behind nginx you can set PRIVATE_MEDIA_X_ACCEL=/protected/ and
let nginx serve the bytes after Django has done the permission check.
"""
import mimetypes
import os
import re

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
CHUNK = 64 * 1024


def _iter_range(fh, start, length):
    remaining = length
    try:
        fh.seek(start)
        while remaining > 0:
            data = fh.read(min(CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data
    finally:
        fh.close()


def serve_private_file(request, field_file, *, download_name=None, content_type=None):
    if not field_file:
        raise Http404("File not found")
    storage = field_file.storage
    name = field_file.name
    if not storage.exists(name):
        raise Http404("File not found")

    content_type = content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
    size = storage.size(name)
    disposition = "attachment" if download_name else "inline"
    filename = download_name or os.path.basename(name)

    x_accel = getattr(settings, "PRIVATE_MEDIA_X_ACCEL", "")
    if x_accel:
        response = HttpResponse(content_type=content_type)
        response["X-Accel-Redirect"] = f"{x_accel.rstrip('/')}/{name}"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        response["Cache-Control"] = "private, no-store"
        return response

    range_header = request.META.get("HTTP_RANGE", "")
    match = RANGE_RE.fullmatch(range_header.strip()) if range_header else None
    if match and size > 0:
        start_s, end_s = match.groups()
        if start_s == "" and end_s == "":
            match = None
        else:
            if start_s == "":  # suffix range: last N bytes
                length = min(int(end_s), size)
                start, end = size - length, size - 1
            else:
                start = int(start_s)
                end = min(int(end_s), size - 1) if end_s else size - 1
            if start >= size or start > end:
                resp = HttpResponse(status=416)
                resp["Content-Range"] = f"bytes */{size}"
                return resp
            length = end - start + 1
            response = StreamingHttpResponse(
                _iter_range(storage.open(name, "rb"), start, length), status=206, content_type=content_type
            )
            response["Content-Length"] = str(length)
            response["Content-Range"] = f"bytes {start}-{end}/{size}"
    if not match:
        response = FileResponse(storage.open(name, "rb"), content_type=content_type)
        response["Content-Length"] = str(size)

    response["Accept-Ranges"] = "bytes"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
