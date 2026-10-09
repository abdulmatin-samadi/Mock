from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Text evaluation provider returning schema-conformant JSON."""

    name = "base"
    default_model = ""
    #: True only for providers that genuinely analyse audio for pronunciation.
    supports_audio_pronunciation = False

    def __init__(self, *, api_key, model=None, timeout=180, **options):
        self.api_key = api_key
        self.model = model or self.default_model
        self.timeout = timeout
        self.options = options

    @abstractmethod
    def generate_json(self, *, system: str, prompt: str, schema: dict, schema_name: str) -> dict:
        ...


class STTProvider(ABC):
    """Speech-to-text provider."""

    name = "base"
    default_model = ""

    def __init__(self, *, api_key, model=None, timeout=180, **options):
        self.api_key = api_key
        self.model = model or self.default_model
        self.timeout = timeout

    @abstractmethod
    def transcribe(self, *, data: bytes, filename: str, content_type: str) -> str:
        ...
