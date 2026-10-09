import json

from ..exceptions import AIConfigurationError, AIProviderError
from .base import LLMProvider, STTProvider


def _client(api_key, timeout):
    try:
        import openai
    except ImportError as e:  # pragma: no cover
        raise AIConfigurationError("The 'openai' package is not installed.") from e
    if not api_key:
        raise AIConfigurationError("No API key configured for the OpenAI provider.")
    return openai, openai.OpenAI(api_key=api_key, timeout=timeout, max_retries=2)


def _translate(openai, e, what):
    if isinstance(e, openai.AuthenticationError):
        return AIConfigurationError(f"OpenAI rejected the API key ({what}).")
    if isinstance(e, openai.NotFoundError):
        return AIConfigurationError(f"OpenAI model not found ({what}).")
    if isinstance(e, openai.RateLimitError):
        if getattr(e, "code", None) in ("insufficient_quota", "credit_balance_exhausted"):
            return AIConfigurationError("The OpenAI account has no credits left — add credits in OpenAI billing.")
        return AIProviderError("OpenAI rate limit reached; try again shortly.", retryable=True)
    if isinstance(e, openai.BadRequestError):
        return AIProviderError(f"OpenAI rejected the request ({what}).")
    if isinstance(e, openai.APIStatusError):
        return AIProviderError(f"OpenAI API error {e.status_code} ({what}).", retryable=e.status_code >= 500)
    if isinstance(e, openai.APIConnectionError):
        return AIProviderError("Could not reach the OpenAI API.", retryable=True)
    return AIProviderError(f"OpenAI error ({what}).")


class OpenAIProvider(LLMProvider):
    name = "openai"
    default_model = "gpt-4o"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._openai, self.client = _client(self.api_key, self.timeout)

    def generate_json(self, *, system, prompt, schema, schema_name):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                response_format={"type": "json_schema",
                                 "json_schema": {"name": schema_name, "schema": schema, "strict": True}},
            )
        except self._openai.OpenAIError as e:
            raise _translate(self._openai, e, "evaluation") from e
        message = response.choices[0].message
        if getattr(message, "refusal", None):
            raise AIProviderError("The AI model declined to evaluate this response.")
        if response.choices[0].finish_reason == "length":
            raise AIProviderError("The AI response was cut off.", retryable=True)
        try:
            return json.loads(message.content or "")
        except json.JSONDecodeError as e:
            raise AIProviderError("The AI returned invalid JSON.", retryable=True) from e


class OpenAISTTProvider(STTProvider):
    name = "openai"
    default_model = "whisper-1"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._openai, self.client = _client(self.api_key, self.timeout)

    def transcribe(self, *, data, filename, content_type):
        try:
            result = self.client.audio.transcriptions.create(
                model=self.model, file=(filename, data, content_type), language="en",
            )
        except self._openai.OpenAIError as e:
            raise _translate(self._openai, e, "transcription") from e
        return (getattr(result, "text", "") or "").strip()
