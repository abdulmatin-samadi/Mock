class AIError(Exception):
    """Base class for AI pipeline errors. Messages are safe to show to admins."""

    retryable = False


class AIConfigurationError(AIError):
    """Provider not configured (missing key, unknown provider, missing SDK)."""


class AIProviderError(AIError):
    """The provider call failed or returned an unusable response."""

    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable
