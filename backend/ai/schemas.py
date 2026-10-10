"""JSON Schemas the AI must return (enforced by the providers' structured-output
features and re-validated in AIService)."""

_CORRECTION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["original", "correction", "explanation"],
    "properties": {
        "original": {"type": "string", "description": "Exact text copied from the student's response"},
        "correction": {"type": "string"},
        "explanation": {"type": "string"},
    },
}

_WEAK = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sentence", "issue", "improved_version"],
    "properties": {
        "sentence": {"type": "string"},
        "issue": {"type": "string"},
        "improved_version": {"type": "string"},
    },
}

_STRONG = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sentence", "reason"],
    "properties": {"sentence": {"type": "string"}, "reason": {"type": "string"}},
}

_CEFR = {"type": "string", "enum": ["A1", "A2", "B1", "B2", "C1", "C2"]}

WRITING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "task_score", "coherence_score", "vocabulary_score", "grammar_score", "overall_score", "cefr_level",
        "task_feedback", "coherence_feedback", "vocabulary_feedback", "grammar_feedback", "detailed_feedback",
        "grammar_mistakes", "vocabulary_mistakes", "suggested_corrections", "weak_sentences", "strong_sentences",
        "improvement_suggestions",
    ],
    "properties": {
        "task_score": {"type": "number"},
        "coherence_score": {"type": "number"},
        "vocabulary_score": {"type": "number"},
        "grammar_score": {"type": "number"},
        "overall_score": {"type": "number"},
        "cefr_level": _CEFR,
        "task_feedback": {"type": "string"},
        "coherence_feedback": {"type": "string"},
        "vocabulary_feedback": {"type": "string"},
        "grammar_feedback": {"type": "string"},
        "detailed_feedback": {"type": "string"},
        "grammar_mistakes": {"type": "array", "items": _CORRECTION},
        "vocabulary_mistakes": {"type": "array", "items": _CORRECTION},
        "suggested_corrections": {"type": "array", "items": _CORRECTION},
        "weak_sentences": {"type": "array", "items": _WEAK},
        "strong_sentences": {"type": "array", "items": _STRONG},
        "improvement_suggestions": {"type": "array", "items": {"type": "string"}},
    },
}

SPEAKING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "fluency_score", "vocabulary_score", "grammar_score", "overall_score", "cefr_level", "fluency_feedback",
        "coherence_feedback", "vocabulary_feedback", "grammar_feedback", "detailed_feedback", "mistakes",
        "improvement_suggestions",
    ],
    "properties": {
        "fluency_score": {"type": "number"},
        "vocabulary_score": {"type": "number"},
        "grammar_score": {"type": "number"},
        "overall_score": {"type": "number"},
        "cefr_level": _CEFR,
        "fluency_feedback": {"type": "string"},
        "coherence_feedback": {"type": "string"},
        "vocabulary_feedback": {"type": "string"},
        "grammar_feedback": {"type": "string"},
        "detailed_feedback": {"type": "string"},
        "mistakes": {"type": "array", "items": _CORRECTION},
        "improvement_suggestions": {"type": "array", "items": {"type": "string"}},
    },
}


EXPLANATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["explanation"],
    "properties": {"explanation": {"type": "string"}},
}
