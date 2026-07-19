"""Website Cloner v2 — modular core package.

This package extracts the v1 engine into focused, testable modules
following the cloner-v2-spec.md contract. The v1 CLI and Web UI continue
to work through thin shims in cloner.py and app.py.
"""

from .config import Config, CONTENT_TYPE_EXT, KNOWN_EXTS, ASSET_ATTRS
from .exceptions import (
    WebCrawlError,
    PrivateIPError,
    SchemeError,
    PathTraversalError,
    AssetTooLargeError,
    MaxSizeExceededError,
)
from .security import is_private_ip, validate_scheme, safe_path
from .rewriter import URLRewriter
from .storage import Storage
from .fetcher import HTTPFetcher, PlaywrightFetcher, ParallelFetcher
from .processor import HTMLProcessor, CSSProcessor
from .crawler import WebsiteCloner

# Convenience functions (keep API same as v1)
from .crawler import clone_website_job, clone_website, main

__all__ = [
    # Config
    "Config",
    "CONTENT_TYPE_EXT",
    "KNOWN_EXTS",
    "ASSET_ATTRS",
    # Exceptions
    "WebCrawlError",
    "PrivateIPError",
    "SchemeError",
    "PathTraversalError",
    "AssetTooLargeError",
    "MaxSizeExceededError",
    # Security
    "is_private_ip",
    "validate_scheme",
    "safe_path",
    # Core modules
    "URLRewriter",
    "Storage",
    "WebsiteCloner",
    "HTTPFetcher",
    "PlaywrightFetcher",
    "ParallelFetcher",
    "HTMLProcessor",
    "CSSProcessor",
    # Convenience
    "clone_website_job",
    "clone_website",
    "main",
]
