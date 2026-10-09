from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User


class Command(BaseCommand):
    help = "Delete free-trial guest accounts (and their attempts) older than --days (default 30)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, days, **options):
        cutoff = timezone.now() - timedelta(days=days)
        old = User.objects.filter(is_guest=True, date_joined__lt=cutoff)
        n = old.count()
        old.delete()
        self.stdout.write(f"Deleted {n} guest account{'s' if n != 1 else ''} older than {days} days.")
