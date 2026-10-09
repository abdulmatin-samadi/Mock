"""Short motivational quotes for the sidebar card (one per day, same for everyone)."""
from django.utils import timezone

QUOTES = [
    ("You don't have to be great to start, but you have to start to be great.", "Zig Ziglar"),
    ("The limits of my language mean the limits of my world.", "Ludwig Wittgenstein"),
    ("Education is the most powerful weapon which you can use to change the world.", "Nelson Mandela"),
    ("One language sets you in a corridor for life. Two languages open every door along the way.", "Frank Smith"),
    ("Success is the sum of small efforts, repeated day in and day out.", "Robert Collier"),
    ("A different language is a different vision of life.", "Federico Fellini"),
]


def quote_of_the_day(day=None):
    day = day or timezone.localdate()
    text, author = QUOTES[day.toordinal() % len(QUOTES)]
    return {"text": text, "author": author}
