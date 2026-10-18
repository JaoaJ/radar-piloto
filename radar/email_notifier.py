"""Future email delivery boundary; no provider or paid service is required today."""

from typing import Any, Protocol


class EmailNotifier(Protocol):
    def send(self, items: list[dict[str, Any]]) -> None:
        """Deliver a digest using a future email provider integration."""


class EmailNotConfigured(RuntimeError):
    """Raised until an email provider is deliberately configured."""