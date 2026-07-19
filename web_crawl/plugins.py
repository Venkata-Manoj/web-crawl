"""Plugin base class for Website Cloner v2 (stub / v2.1+)."""

from abc import ABC, abstractmethod
from typing import Any


class Plugin(ABC):
    """Base class for Website Cloner plugins.

    Plugin hooks are called at each stage of the crawl lifecycle.
    v2.0 ships only the stub — actual hooks are deferred to v2.1+.
    """

    name: str = "unnamed"

    @abstractmethod
    def after_html(self, url: str, html: str, context: dict[str, Any]) -> str:
        """Called after HTML is fetched but before rewriting."""

    @abstractmethod
    def map_url(self, url: str, context: dict[str, Any]) -> str:
        """Called for each discovered URL during crawling."""

    @abstractmethod
    def export(self, output_dir: str, context: dict[str, Any]) -> None:
        """Called after the clone is complete for custom export."""
