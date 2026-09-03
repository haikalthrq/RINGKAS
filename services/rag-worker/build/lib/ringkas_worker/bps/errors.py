class BpsClientError(Exception):
    """Base class for safe, typed BPS client failures."""


class BpsConfigurationError(BpsClientError):
    """The client is not configured for a request."""


class BpsAuthenticationError(BpsClientError):
    """An injected authentication adapter failed without exposing its details."""


class BpsUpstreamError(BpsClientError):
    """The upstream returned a non-success HTTP response."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"BPS upstream returned HTTP status {status_code}")
        self.status_code = status_code


class BpsTimeoutError(BpsClientError):
    """The upstream request exceeded its configured timeout."""


class BpsNetworkError(BpsClientError):
    """The request failed before a usable HTTP response was received."""


class BpsInvalidJsonError(BpsClientError):
    """The upstream response was not valid JSON."""


class BpsResponseShapeError(BpsClientError):
    """The placeholder response did not have the expected container shape."""


class BpsInvalidMetadataError(BpsClientError):
    """A response item did not contain sufficient valid metadata."""
