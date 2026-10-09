"""AIService — the only entry point the rest of the project uses for AI.

    AIService().evaluate_writing(task=..., essay=..., word_count=...)
    AIService().transcribe_speaking(field_file)
    AIService().evaluate_speaking(question=..., transcript=..., duration=...)

Providers are chosen from settings (AI_PROVIDER / STT_PROVIDER) so the vendor can
be swapped without touching views or models. All scores returned by the model are
validated, clamped and re-aggregated here on the server.
"""
import os
from decimal import ROUND_HALF_UP, Decimal
from statistics import mean

from django.conf import settings

from core.validators import AUDIO_CONTENT_TYPES
from exams.scoring import MAX_SCORE, multilevel_to_cefr, round_score

from . import prompts
from .exceptions import AIConfigurationError, AIProviderError
from .providers.anthropic_provider import AnthropicProvider
from .providers.gemini_provider import GeminiProvider, GeminiSTTProvider
from .providers.openai_provider import OpenAIProvider, OpenAISTTProvider
from .schemas import SPEAKING_SCHEMA, WRITING_SCHEMA

LLM_PROVIDERS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider, "gemini": GeminiProvider}
STT_PROVIDERS = {"openai": OpenAISTTProvider, "gemini": GeminiSTTProvider}

def get_llm_provider():
    cls = LLM_PROVIDERS.get(settings.AI_PROVIDER)
    if cls is None:
        raise AIConfigurationError(f"Unknown AI_PROVIDER '{settings.AI_PROVIDER}'. "
                                   f"Choose one of: {', '.join(LLM_PROVIDERS)}.")
    return cls(api_key=settings.AI_API_KEY, model=settings.AI_MODEL or None, timeout=settings.AI_TIMEOUT,
               effort=settings.AI_EFFORT)


def get_stt_provider():
    cls = STT_PROVIDERS.get(settings.STT_PROVIDER)
    if cls is None:
        raise AIConfigurationError(f"Unknown STT_PROVIDER '{settings.STT_PROVIDER}'. "
                                   f"Choose one of: {', '.join(STT_PROVIDERS)}.")
    return cls(api_key=settings.STT_API_KEY, model=settings.STT_MODEL or None, timeout=settings.AI_TIMEOUT)


def _clamp_score(value):
    """Validate an AI score and clamp it to the Multilevel 0–75 scale."""
    try:
        v = Decimal(str(value))
    except Exception:
        raise AIProviderError("The AI returned a non-numeric score.", retryable=True)
    return round_score(max(Decimal(0), min(MAX_SCORE, v)))


def _overall(scores):
    """Overall = mean of criterion scores, recomputed on the server."""
    return round_score(mean(float(s) for s in scores))


def _clean_list(items, keys, limit):
    out = []
    for item in (items or [])[:limit]:
        if isinstance(item, dict):
            out.append({k: str(item.get(k, ""))[:1000] for k in keys})
    return out


def _clean_strings(items, limit):
    return [str(s)[:600] for s in (items or [])[:limit] if str(s).strip()]


class AIService:
    def __init__(self, llm=None, stt=None):
        self._llm = llm
        self._stt = stt

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_provider()
        return self._llm

    @property
    def stt(self):
        if self._stt is None:
            self._stt = get_stt_provider()
        return self._stt

    # ------------------------------------------------------------- writing
    def evaluate_writing(self, *, task, essay, word_count):
        data = self.llm.generate_json(
            system=prompts.writing_system_prompt(),
            prompt=prompts.writing_user_prompt(task, essay, word_count),
            schema=WRITING_SCHEMA,
            schema_name="writing_evaluation",
        )
        try:
            criteria = {k: _clamp_score(data[k])
                        for k in ("task_score", "coherence_score", "vocabulary_score", "grammar_score")}
        except KeyError as e:
            raise AIProviderError(f"AI response is missing '{e.args[0]}'.", retryable=True)
        overall = _overall(criteria.values())
        return {
            "provider": self.llm.name,
            "model_name": self.llm.model,
            **criteria,
            "overall_score": overall,
            "cefr_level": multilevel_to_cefr(overall),
            "task_feedback": str(data.get("task_feedback", "")),
            "coherence_feedback": str(data.get("coherence_feedback", "")),
            "vocabulary_feedback": str(data.get("vocabulary_feedback", "")),
            "grammar_feedback": str(data.get("grammar_feedback", "")),
            "detailed_feedback": str(data.get("detailed_feedback", "")),
            "grammar_mistakes": _clean_list(data.get("grammar_mistakes"), ("original", "correction", "explanation"), 20),
            "vocabulary_mistakes": _clean_list(data.get("vocabulary_mistakes"),
                                               ("original", "correction", "explanation"), 20),
            "suggested_corrections": _clean_list(data.get("suggested_corrections"),
                                                 ("original", "correction", "explanation"), 15),
            "weak_sentences": _clean_list(data.get("weak_sentences"), ("sentence", "issue", "improved_version"), 8),
            "strong_sentences": _clean_list(data.get("strong_sentences"), ("sentence", "reason"), 8),
            "improvement_suggestions": _clean_strings(data.get("improvement_suggestions"), 10),
            "raw_response": data,
        }

    @staticmethod
    def empty_writing_result(task):
        """Deterministic result for a blank answer — no AI call is needed to score nothing."""
        zero = Decimal("0")
        return {
            "provider": "rule", "model_name": "empty-response",
            "task_score": zero, "coherence_score": zero, "vocabulary_score": zero, "grammar_score": zero,
            "overall_score": zero, "cefr_level": "",
            "task_feedback": "No response was submitted for this task.", "coherence_feedback": "",
            "vocabulary_feedback": "", "grammar_feedback": "",
            "detailed_feedback": "No response was submitted, so this task scores zero.",
            "grammar_mistakes": [], "vocabulary_mistakes": [], "suggested_corrections": [], "weak_sentences": [],
            "strong_sentences": [],
            "improvement_suggestions": ["Always attempt every task — even a partial answer earns marks."],
            "raw_response": {},
        }

    # ------------------------------------------------------------ speaking
    def transcribe_speaking(self, field_file):
        name = os.path.basename(field_file.name)
        ext = os.path.splitext(name)[1].lower()
        field_file.open("rb")
        try:
            data = field_file.read()
        finally:
            field_file.close()
        text = self.stt.transcribe(data=data, filename=name,
                                   content_type=AUDIO_CONTENT_TYPES.get(ext, "application/octet-stream"))
        return {"text": text, "provider": self.stt.name, "model": self.stt.model}

    def evaluate_speaking(self, *, question, transcript, duration):
        data = self.llm.generate_json(
            system=prompts.speaking_system_prompt(),
            prompt=prompts.speaking_user_prompt(question, transcript, duration),
            schema=SPEAKING_SCHEMA,
            schema_name="speaking_evaluation",
        )
        try:
            criteria = {k: _clamp_score(data[k]) for k in ("fluency_score", "vocabulary_score", "grammar_score")}
        except KeyError as e:
            raise AIProviderError(f"AI response is missing '{e.args[0]}'.", retryable=True)
        overall = _overall(criteria.values())
        pronunciation_supported = bool(getattr(self.llm, "supports_audio_pronunciation", False))
        return {
            "provider": self.llm.name,
            "model_name": self.llm.model,
            **criteria,
            "overall_score": overall,
            "cefr_level": multilevel_to_cefr(overall),
            "pronunciation_assessed": pronunciation_supported,
            "pronunciation_score": None,
            "pronunciation_feedback": (
                "" if pronunciation_supported else
                "Pronunciation was not assessed: the configured AI provider evaluates a speech-to-text transcript, "
                "not the audio itself. The overall score is based on fluency & coherence, lexical resource and "
                "grammar only."
            ),
            "fluency_feedback": str(data.get("fluency_feedback", "")),
            "coherence_feedback": str(data.get("coherence_feedback", "")),
            "vocabulary_feedback": str(data.get("vocabulary_feedback", "")),
            "grammar_feedback": str(data.get("grammar_feedback", "")),
            "detailed_feedback": str(data.get("detailed_feedback", "")),
            "mistakes": _clean_list(data.get("mistakes"), ("original", "correction", "explanation"), 20),
            "improvement_suggestions": _clean_strings(data.get("improvement_suggestions"), 10),
            "raw_response": data,
        }

    @staticmethod
    def empty_speaking_result(question):
        zero = Decimal("0")
        return {
            "provider": "rule", "model_name": "no-speech",
            "fluency_score": zero, "vocabulary_score": zero, "grammar_score": zero, "overall_score": zero,
            "cefr_level": "", "pronunciation_assessed": False, "pronunciation_score": None,
            "pronunciation_feedback": "Pronunciation was not assessed.",
            "fluency_feedback": "No speech was detected in the recording.", "coherence_feedback": "",
            "vocabulary_feedback": "", "grammar_feedback": "",
            "detailed_feedback": "The recording contained no recognisable English speech, so it scores zero. "
                                 "Check your microphone and speak clearly.",
            "mistakes": [], "improvement_suggestions": ["Make sure your microphone works before you start."],
            "raw_response": {},
        }

    # -------------------------------------------------------------- status
    @staticmethod
    def status():
        """Configuration overview for the admin settings page (never exposes keys)."""
        info = {
            "provider": settings.AI_PROVIDER,
            "model": settings.AI_MODEL or getattr(LLM_PROVIDERS.get(settings.AI_PROVIDER), "default_model", "?"),
            "api_key_set": bool(settings.AI_API_KEY),
            "stt_provider": settings.STT_PROVIDER,
            "stt_model": settings.STT_MODEL or getattr(STT_PROVIDERS.get(settings.STT_PROVIDER), "default_model", "?"),
            "stt_key_set": bool(settings.STT_API_KEY),
            "task_mode": settings.AI_TASK_MODE,
            "pronunciation_supported": bool(getattr(LLM_PROVIDERS.get(settings.AI_PROVIDER),
                                                    "supports_audio_pronunciation", False)),
            "errors": [],
        }
        try:
            get_llm_provider()
        except AIConfigurationError as e:
            info["errors"].append(str(e))
        try:
            get_stt_provider()
        except AIConfigurationError as e:
            info["errors"].append(f"Speech-to-text: {e}")
        return info
