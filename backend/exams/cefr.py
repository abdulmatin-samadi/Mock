"""Official Multilevel (CEFR) structure for Reading and Listening.

Used by the admin dashboard to lay out new mocks part by part and to offer
only the question types each part uses.
"""

READING_PARTS = [
    {"code": "R1", "title": "Part 1 · Gap filling", "count": 6, "types": ["gap_filling"],
     "instructions": "Read the text. Fill in each gap with ONE word. You must use a word which is somewhere in "
                     "the rest of the text."},
    {"code": "R2", "title": "Part 2 · Matching", "count": 8, "types": ["matching"],
     "instructions": "Read the texts and the statements A–J. Match each text with the correct statement. "
                     "There are two extra statements."},
    {"code": "R3", "title": "Part 3 · Headings", "count": 6, "types": ["headings"],
     "instructions": "Read the text. Choose the correct heading for each paragraph from the list of headings. "
                     "There are two extra headings."},
    {"code": "R4", "title": "Part 4 · Multiple choice & True / False / No Information", "count": 9,
     "types": ["multiple_choice", "true_false_not_given"],
     "instructions": "Read the text. For the first questions choose the correct answer A, B, C or D. Then decide "
                     "if the statements are TRUE, FALSE or NO INFORMATION."},
    {"code": "R5", "title": "Part 5 · Gap filling & multiple choice", "count": 6,
     "types": ["gap_filling", "multiple_choice"],
     "instructions": "Read the text. Fill in the gaps with no more than ONE WORD and/or A NUMBER, then choose the "
                     "correct answer A, B, C or D."},
]

LISTENING_PARTS = [
    {"code": "L1", "title": "Part 1 · Short conversations", "count": 8, "types": ["multiple_choice"],
     "instructions": "You will hear some short conversations. Choose the correct answer A, B or C."},
    {"code": "L2", "title": "Part 2 · Gap filling", "count": 6, "types": ["gap_filling"],
     "instructions": "Listen and complete the notes. Write no more than ONE WORD and/or A NUMBER for each answer."},
    {"code": "L3", "title": "Part 3 · Matching speakers", "count": 5, "types": ["matching"],
     "instructions": "You will hear people talking. Match each speaker to the correct statement. There are "
                     "extra statements."},
    {"code": "L4", "title": "Part 4 · Map labelling", "count": 5, "types": ["map_labelling"],
     "instructions": "Look at the map. Choose the correct letter for each place."},
    {"code": "L5", "title": "Part 5 · Multiple choice (extracts)", "count": 6, "types": ["multiple_choice"],
     "instructions": "You will hear some extracts. Choose the correct answer A, B or C."},
    {"code": "L6", "title": "Part 6 · Gap filling (lecture)", "count": 6, "types": ["gap_filling"],
     "instructions": "Listen to part of a lecture and complete the notes. Write no more than ONE WORD for each "
                     "answer."},
]

PARTS = {p["code"]: p for p in READING_PARTS + LISTENING_PARTS}
PART_CHOICES = [("", "Custom part")] + [
    (p["code"], f"{'Reading' if p['code'][0] == 'R' else 'Listening'} — {p['title']}")
    for p in READING_PARTS + LISTENING_PARTS
]


def structure(section):
    return READING_PARTS if section == "reading" else LISTENING_PARTS if section == "listening" else []


def allowed_types(part):
    preset = PARTS.get(getattr(part, "cefr_part", "") or "")
    return preset["types"] if preset else None
