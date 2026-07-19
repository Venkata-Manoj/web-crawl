"""Custom exceptions for Website Cloner v2."""


class WebCrawlError(Exception):
    """Base exception for all web crawl errors."""


class PrivateIPError(WebCrawlError):
    """Raised when a URL resolves to a private/loopback IP."""


class SchemeError(WebCrawlError):
    """Raised when a URL has an unsupported scheme."""


class PathTraversalError(WebCrawlError):
    """Raised when a path escapes the output directory."""


class AssetTooLargeError(WebCrawlError):
    """Raised when a single asset exceeds the size limit."""


class MaxSizeExceededError(WebCrawlError):
    """Raised when total download size exceeds the limit."""
