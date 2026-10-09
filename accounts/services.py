from django.contrib.auth.forms import PasswordResetForm
from django.db import transaction

from .models import User


@transaction.atomic
def register_user(*, email, password, first_name, last_name, **profile):
    """Self-registration always creates a student. Nobody can self-register as admin."""
    return User.objects.create_user(
        email=email, password=password, first_name=first_name, last_name=last_name, role=User.Role.STUDENT,
        **profile,
    )


def send_password_reset(request, email):
    """Sends a reset link (if the email exists). Never reveals whether it does."""
    form = PasswordResetForm(data={"email": email})
    if form.is_valid():
        form.save(
            request=request,
            use_https=request.is_secure(),
            email_template_name="accounts/emails/password_reset_email.txt",
            subject_template_name="accounts/emails/password_reset_subject.txt",
        )
