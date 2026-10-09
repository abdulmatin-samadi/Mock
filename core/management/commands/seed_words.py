"""Load a starter list of B2–C1 words for the "Word of the day" card.
Admins can add, edit or deactivate words in /django-admin/core/word/."""
from django.core.management.base import BaseCommand

from core.models import Word

WORDS = [
    ("precarious", "/prɪˈkeəriəs/", "adjective", "not securely held or in position; likely to collapse or fail",
     "Many young people are in precarious employment.", "C1"),
    ("ubiquitous", "/juːˈbɪkwɪtəs/", "adjective", "seeming to be everywhere", "Smartphones have become ubiquitous.", "C1"),
    ("mitigate", "/ˈmɪtɪɡeɪt/", "verb", "to make something less harmful, serious or painful",
     "Trees help to mitigate the effects of pollution.", "C1"),
    ("profound", "/prəˈfaʊnd/", "adjective", "very great or intense; showing deep understanding",
     "The internet has had a profound impact on education.", "B2"),
    ("detrimental", "/ˌdetrɪˈmentl/", "adjective", "causing harm or damage",
     "Lack of sleep is detrimental to your health.", "C1"),
    ("feasible", "/ˈfiːzəbl/", "adjective", "possible and practical to do", "Is it feasible to finish by Friday?", "B2"),
    ("inevitable", "/ɪnˈevɪtəbl/", "adjective", "certain to happen and impossible to avoid",
     "Some changes in technology are inevitable.", "B2"),
    ("alleviate", "/əˈliːvieɪt/", "verb", "to make suffering or a problem less severe",
     "New roads may alleviate traffic congestion.", "C1"),
    ("diminish", "/dɪˈmɪnɪʃ/", "verb", "to become or make something smaller or less important",
     "His influence diminished over time.", "B2"),
    ("compelling", "/kəmˈpelɪŋ/", "adjective", "very convincing or interesting",
     "She made a compelling argument for change.", "C1"),
    ("scrutinise", "/ˈskruːtənaɪz/", "verb", "to examine something very carefully",
     "Examiners scrutinise every answer.", "C1"),
    ("deteriorate", "/dɪˈtɪəriəreɪt/", "verb", "to become worse", "Air quality deteriorates in winter.", "B2"),
    ("substantial", "/səbˈstænʃl/", "adjective", "large in size, value or importance",
     "There has been a substantial increase in prices.", "B2"),
    ("advocate", "/ˈædvəkeɪt/", "verb", "to publicly support or recommend",
     "Doctors advocate regular exercise.", "C1"),
    ("ambiguous", "/æmˈbɪɡjuəs/", "adjective", "having more than one possible meaning",
     "The question was ambiguous.", "C1"),
    ("consequently", "/ˈkɒnsɪkwəntli/", "adverb", "as a result", "He missed the bus and consequently arrived late.", "B2"),
    ("crucial", "/ˈkruːʃl/", "adjective", "extremely important; decisive", "Practice is crucial to success.", "B2"),
    ("enhance", "/ɪnˈhɑːns/", "verb", "to improve the quality or value of something",
     "Reading enhances your vocabulary.", "B2"),
    ("hinder", "/ˈhɪndə(r)/", "verb", "to make it difficult for something to happen",
     "Poor internet can hinder online learning.", "C1"),
    ("notion", "/ˈnəʊʃn/", "noun", "an idea, belief or understanding", "I reject the notion that exams are useless.", "B2"),
    ("pervasive", "/pəˈveɪsɪv/", "adjective", "spreading widely through an area or group",
     "Advertising is pervasive in modern life.", "C1"),
    ("reluctant", "/rɪˈlʌktənt/", "adjective", "unwilling and hesitant", "She was reluctant to speak in public.", "B2"),
    ("sustainable", "/səˈsteɪnəbl/", "adjective", "able to continue without damaging the environment",
     "Cities need sustainable transport.", "B2"),
    ("tangible", "/ˈtændʒəbl/", "adjective", "real and able to be shown or felt",
     "The project produced tangible results.", "C1"),
    ("versatile", "/ˈvɜːsətaɪl/", "adjective", "able to adapt to many different uses or activities",
     "English is a versatile language.", "C1"),
    ("acquire", "/əˈkwaɪə(r)/", "verb", "to gain knowledge or skill; to obtain",
     "Children acquire languages quickly.", "B2"),
    ("controversial", "/ˌkɒntrəˈvɜːʃl/", "adjective", "causing a lot of public disagreement",
     "The new law is highly controversial.", "B2"),
    ("emphasise", "/ˈemfəsaɪz/", "verb", "to give special importance to something",
     "The teacher emphasised the need for practice.", "B2"),
    ("resilient", "/rɪˈzɪliənt/", "adjective", "able to recover quickly from difficulties",
     "Resilient students learn from failure.", "C1"),
    ("unprecedented", "/ʌnˈpresɪdentɪd/", "adjective", "never having happened before",
     "The city saw unprecedented growth.", "C1"),
]


class Command(BaseCommand):
    help = "Add a starter list of vocabulary words for the Word of the day card."

    def handle(self, *args, **opts):
        created = 0
        for word, ipa, pos, definition, example, level in WORDS:
            _, new = Word.objects.get_or_create(word=word, defaults={
                "ipa": ipa, "part_of_speech": pos, "definition": definition, "example": example, "level": level})
            created += new
        self.stdout.write(self.style.SUCCESS(f"Added {created} word(s); {Word.objects.count()} in total."))
