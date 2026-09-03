class EmbeddingClientError(Exception):
    """Base class for safe, typed embedding client failures."""


class EmbeddingConfigurationError(EmbeddingClientError):
    """Required embedding configuration is missing or unsafe."""


class EmbeddingAuthenticationError(EmbeddingClientError):
    """The provider rejected the configured credentials."""


class EmbeddingRateLimitError(EmbeddingClientError):
    """The provider rate-limited the request."""


class EmbeddingProviderError(EmbeddingClientError):
    """The provider returned a non-success response."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"embedding provider returned HTTP status {status_code}")
        self.status_code = status_code


class EmbeddingTimeoutError(EmbeddingClientError):
    """The provider request exceeded its configured timeout."""


class EmbeddingCancellationError(EmbeddingClientError):
    """The provider request was cancelled."""


class EmbeddingTransportError(EmbeddingClientError):
    """The request failed before a usable response was received."""


class EmbeddingResponseError(EmbeddingClientError):
    """The provider response was invalid JSON or violated the response schema."""


def raise_sanitized(error: EmbeddingClientError) -> None:
    """Raise an error without retaining provider secrets or raw exceptions."""
    error.__cause__ = None
    error.__context__ = None
    raise error
