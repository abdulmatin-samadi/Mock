"""Guest trial: a visitor can take ONE mock without an account.

Starting a mock while logged out creates a temporary guest student and logs it in.
Registering turns that guest into the real account; logging in to an existing
account moves the guest's attempts there. Either way the free result is kept.
"""
import uuid

from django.conf import settings
from django.contrib.auth import login
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction

from .models import User

GUEST_FREE_MOCKS = getattr(settings, "GUEST_FREE_MOCKS", 1)
GUEST_ACCOUNTS_PER_IP_PER_DAY = getattr(settings, "GUEST_ACCOUNTS_PER_IP_PER_DAY", 5)


class GuestLimitReached(PermissionDenied):
    """The guest has used the free mock(s); an account is needed to continue."""

    def __init__(self, msg="You've used your free mock. Create a free account to continue."):
        super().__init__(msg)


def _client_ip(request):
    return (request.META.get("REMOTE_ADDR") or "unknown")[:64]


def start_guest(request):
    """Return a guest student for this visitor (creating and logging it in). None if this IP made too many."""
    key = f"guest-accounts:{_client_ip(request)}"
    made = cache.get(key, 0)
    if made >= GUEST_ACCOUNTS_PER_IP_PER_DAY:
        return None
    user = User.objects.create_user(email=f"guest-{uuid.uuid4().hex[:16]}@guest.invalid", password=None,
                                    first_name="Guest", last_name="", is_guest=True)
    cache.set(key, made + 1, 24 * 3600)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return user


def check_can_start(user):
    """Guests may start only GUEST_FREE_MOCKS new attempts (resuming an unfinished one is always fine)."""
    from results.models import ExamAttempt

    if getattr(user, "is_guest", False) and ExamAttempt.objects.filter(student=user).count() >= GUEST_FREE_MOCKS:
        raise GuestLimitReached


@transaction.atomic
def convert_guest(guest, *, email, password, first_name, last_name):
    """Turn the guest into a normal student account; its attempts stay where they are."""
    guest.email = email
    guest.first_name, guest.last_name = first_name, last_name
    guest.is_guest = False
    guest.set_password(password)
    guest.save()
    return guest


@transaction.atomic
def merge_guest_into(guest, user):
    """Move everything the guest did to `user` and delete the guest."""
    if not guest or not getattr(guest, "is_guest", False) or guest.pk == user.pk:
        return 0
    from results.models import ExamAttempt, FullMockAttempt
    from speaking.models import SpeakingSubmission
    from writing.models import WritingSubmission

    moved = ExamAttempt.objects.filter(student=guest).update(student=user)
    FullMockAttempt.objects.filter(student=guest).update(student=user)
    WritingSubmission.objects.filter(student=guest).update(student=user)
    SpeakingSubmission.objects.filter(student=guest).update(student=user)
    guest.delete()
    return moved
