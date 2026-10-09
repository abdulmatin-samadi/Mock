from django.db import models
from django.utils import timezone


class Word(models.Model):
    """Vocabulary item for the "Word of the day" card. Managed by admins."""

    word = models.CharField(max_length=80, unique=True)
    ipa = models.CharField("Pronunciation (IPA)", max_length=80, blank=True)
    part_of_speech = models.CharField(max_length=30, blank=True)
    definition = models.TextField()
    example = models.TextField(blank=True)
    level = models.CharField(max_length=2, blank=True, help_text="CEFR level, e.g. B2")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.word

    @classmethod
    def of_the_day(cls, day=None):
        """Same word for everyone on a given date; rotates through active words."""
        ids = list(cls.objects.filter(is_active=True).values_list("id", flat=True))
        if not ids:
            return None
        day = day or timezone.localdate()
        return cls.objects.get(pk=ids[day.toordinal() % len(ids)])
