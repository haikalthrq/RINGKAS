"""Configurable, internal BPS publication metadata client boundary."""

__all__ = ["BpsClient", "PublicationMetadata"]


def __getattr__(name: str):
    if name == "BpsClient":
        from ringkas_worker.bps.client import BpsClient

        return BpsClient
    if name == "PublicationMetadata":
        from ringkas_worker.bps.models import PublicationMetadata

        return PublicationMetadata
    raise AttributeError(name)
