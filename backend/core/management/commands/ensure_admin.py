"""Create the first admin from ADMIN_EMAIL / ADMIN_PASSWORD (for hosts without a shell, e.g. Render free).

Safe to run on every start: an existing account is left alone, so a password changed later in the
admin panel is never overwritten.
"""
import os

from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = "Create an admin from the ADMIN_EMAIL and ADMIN_PASSWORD environment variables if it does not exist."

    def handle(self, *args, **options):
        email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
        password = os.environ.get("ADMIN_PASSWORD") or ""
        if not email or not password:
            self.stdout.write("ensure_admin: ADMIN_EMAIL / ADMIN_PASSWORD not set, skipping.")
            return
        if User.objects.filter(email__iexact=email).exists():
            self.stdout.write(f"ensure_admin: {email} already exists.")
            return
        User.objects.create_superuser(email=email, password=password, first_name="Site", last_name="Admin")
        self.stdout.write(f"ensure_admin: created admin {email}.")
