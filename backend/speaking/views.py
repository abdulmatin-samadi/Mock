from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from core.media import serve_private_file

from .models import SpeakingSubmission
from .services import can_access_recording


@login_required
def recording_audio(request, pk):
    """Stream a speaking recording — only to its owner or an admin."""
    sub = get_object_or_404(SpeakingSubmission, pk=pk)
    if not can_access_recording(request.user, sub):
        raise PermissionDenied
    return serve_private_file(request, sub.audio_file, content_type=sub.mime_type or None)
