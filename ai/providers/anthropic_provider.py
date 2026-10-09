import json
import logging

from ..exceptions import AIConfigurationError, AIProviderError
from .base import LLMProvider

logger = logging.getLogger(__name__)

# Models that accept the server-side refusal fallback (`fallbacks: "default"`).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-opus-5-5"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise AIConfigurationError("The 'anthropic' package is not installed.") from e
        if not self.api_key:
            raise AIConfigurationError("AI_API_KEY is not set for the Anthropic provider.")
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout, max_retries=2)
        self.effort = self.options.get("effort") or "high"

    def generate_json(self, *, system, prompt, schema, schema_name):
        a = self._anthropic
        output_config = {"format": {"type": "json_schema", "schema": schema}}
        if "haiku" not in self.model:
            output_config["effort"] = self.effort
        kwargs = dict(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config=output_config,
        )
        try:
            if self.model in FALLBACK_MODELS:
                response = self.client.beta.messages.create(
                    **kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            else:
                response = self.client.messages.create(**kwargs)
        except a.AuthenticationError as e:
            raise AIConfigurationError("Anthropic rejected the API key.") from e
        except a.NotFoundError as e:
            raise AIConfigurationError(f"Anthropic model '{self.model}' was not found.") from e
        except a.RateLimitError as e:
            raise AIProviderError("Anthropic rate limit reached; try again shortly.", retryable=True) from e
        except a.BadRequestError as e:
            raise AIProviderError(f"Anthropic rejected the request: {e.message}") from e
        except a.APIStatusError as e:
            raise AIProviderError(f"Anthropic API error ({e.status_code}).", retryable=e.status_code >= 500) from e
        except a.APIConnectionError as e:
            raise AIProviderError("Could not reach the Anthropic API.", retryable=True) from e

        if response.stop_reason == "refusal":
            raise AIProviderError("The AI model declined to evaluate this response.")
        if response.stop_reason == "max_tokens":
            raise AIProviderError("The AI response was cut off (max_tokens).", retryable=True)
        text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), None)
        if not text:
            raise AIProviderError("The AI returned an empty response.", retryable=True)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise AIProviderError("The AI returned invalid JSON.", retryable=True) from e
