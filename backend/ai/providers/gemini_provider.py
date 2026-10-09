"""Google Gemini (AI Studio API key) — evaluation and speech-to-text.

Uses the REST endpoint directly through httpx2 (already installed with the
openai/anthropic SDKs), so no extra package is needed. Keys come from
https://aistudio.google.com/apikey (a free tier with rate limits is available).
"""
import base64
import json
import time

import httpx2  # ships with the openai/anthropic SDKs and bundles CA certificates

from ..exceptions import AIConfigurationError, AIProviderError
from .base import LLMProvider, STTProvider

# Inline audio must keep the whole request under 20 MB (base64 adds ~33%).
INLINE_AUDIO_LIMIT = 14 * 1024 * 1024
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


# Gemini often answers 503 "high demand" (and 429 on the free tier); these
# usually clear within seconds, so retry a couple of times before failing.
RETRY_DELAYS = (4, 12)


def _post(api_key, model, body, timeout, what):
    if not api_key:
        raise AIConfigurationError("No API key configured for the Gemini provider.")
    for delay in RETRY_DELAYS:
        try:
            return _post_once(api_key, model, body, timeout, what)
        except AIProviderError as e:
            if not e.retryable:
                raise
            time.sleep(delay)
    return _post_once(api_key, model, body, timeout, what)


def _post_once(api_key, model, body, timeout, what):
    try:
        response = httpx2.post(API_URL.format(model=model), json=body, timeout=timeout,
                               headers={"x-goog-api-key": api_key})
    except httpx2.TransportError as e:
        raise AIProviderError("Could not reach the Gemini API.", retryable=True) from e
    if response.status_code >= 400:
        raise _translate(response, what)
    try:
        return response.json()
    except ValueError as e:
        raise AIProviderError("Gemini returned an unreadable response.", retryable=True) from e


def _translate(response, what):
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        error = {}
    code = response.status_code
    message = (error.get("message") or "").lower()
    if code in (401, 403) or "api key not valid" in message or "api_key_invalid" in message:
        return AIConfigurationError(f"Gemini rejected the API key ({what}).")
    if code == 404:
        return AIConfigurationError(f"Gemini model not found ({what}) — check AI_MODEL / STT_MODEL.")
    if code == 429:
        return AIProviderError("Gemini quota or rate limit reached; try again later.", retryable=True)
    if code >= 500:
        return AIProviderError(f"Gemini API error {code} ({what}).", retryable=True)
    return AIProviderError(f"Gemini rejected the request ({what}): {error.get('message', '')[:200]}")


def _text(data):
    """Concatenated text of the first candidate, with block/cut-off handling."""
    feedback = data.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        raise AIProviderError("The AI model declined to process this response.")
    candidates = data.get("candidates") or []
    if not candidates:
        raise AIProviderError("Gemini returned no answer.", retryable=True)
    candidate = candidates[0]
    reason = candidate.get("finishReason")
    if reason == "MAX_TOKENS":
        raise AIProviderError("The AI response was cut off.", retryable=True)
    if reason in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST"):
        raise AIProviderError("The AI model declined to process this response.")
    parts = (candidate.get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


class GeminiProvider(LLMProvider):
    name = "gemini"
    # The "gemini-flash-latest" alias timed out in testing (2026-10); pin a model.
    default_model = "gemini-3.5-flash"

    def generate_json(self, *, system, prompt, schema, schema_name):
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema},
        }
        text = _text(_post(self.api_key, self.model, body, self.timeout, "evaluation"))
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise AIProviderError("The AI returned invalid JSON.", retryable=True) from e


class GeminiSTTProvider(STTProvider):
    name = "gemini"
    default_model = "gemini-3.5-flash"

    def transcribe(self, *, data, filename, content_type):
        if len(data) > INLINE_AUDIO_LIMIT:
            raise AIProviderError("The recording is too large for Gemini transcription (max ~18 MB).")
        body = {
            "contents": [{"role": "user", "parts": [
                {"text": "Transcribe this English speech recording verbatim. Return only the transcript text, "
                         "with no commentary. If nothing intelligible is said, return an empty response."},
                {"inline_data": {"mime_type": (content_type or "audio/webm").split(";")[0],
                                 "data": base64.b64encode(data).decode()}},
            ]}],
        }
        return _text(_post(self.api_key, self.model, body, self.timeout, "transcription")).strip()
