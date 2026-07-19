"""URL rewriting and local-path mapping for Website Cloner v2."""

import os
import threading
from typing import Dict, Optional
from urllib.parse import unquote_plus, urlparse, urlunparse

from .config import CONTENT_TYPE_EXT, KNOWN_EXTS


class URLRewriter:
    """Normalise URLs, check domains, and map remote URLs → local file paths.

    Maintains an internal ``url_to_local`` dict for deterministic caching so
    the same URL always produces the same relative path.
    """

    def __init__(self, seed_url: str, lock: Optional[threading.RLock] = None):
        parsed = urlparse(seed_url)
        self.start_domain = parsed.netloc
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        self.url_to_local: Dict[str, str] = {}
        self._lock = lock

    # ------------------------------------------------------------------
    # URL normalisation
    # ------------------------------------------------------------------

    def _normalize_url(self, url: str) -> str:
        """Strip fragment and trailing slash; keep query strings."""
        parsed = urlparse(url)
        normalized = urlunparse(
            parsed._replace(fragment="", path=parsed.path.rstrip("/") or "/")
        )
        return normalized

    # ------------------------------------------------------------------
    # Domain / link-type checks
    # ------------------------------------------------------------------

    def _is_same_domain(self, url: str) -> bool:
        """Return True when *url* belongs to the seed domain."""
        return urlparse(url).netloc == self.start_domain

    def _is_html_link(self, url: str) -> bool:
        """Return True when *url* looks like an HTML page (not a binary asset)."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        if not path or path == "/":
            return True
        ext = os.path.splitext(path)[1]
        if ext in KNOWN_EXTS and ext not in (".html", ".htm", ".php", ".asp", ".aspx"):
            return False
        return True

    # ------------------------------------------------------------------
    # URL → local path mapping (centralised, deterministic)
    # ------------------------------------------------------------------

    def _local_path_for(self, url: str, content_type: Optional[str] = None) -> str:
        """Map a remote URL to a relative local file path.

        Handles URL-encoded query strings (%3F in path → real query separator)
        so filenames stay clean even when upstream CSS uses
        ``url('font.woff?v=...')``.
        """
        lock = self._lock
        if lock:
            lock.acquire()
        try:
            if url in self.url_to_local:
                return self.url_to_local[url]

            parsed = urlparse(url)
            clean_path = unquote_plus(parsed.path)
            if "?" in clean_path:
                clean_path = clean_path.split("?")[0]

            if not clean_path or clean_path == "/":
                local_path = "index.html"
            else:
                local_path = clean_path.lstrip("/")

            ext = os.path.splitext(local_path)[1].lower()

            if not ext or ext not in KNOWN_EXTS:
                if content_type:
                    mime = content_type.split(";")[0].strip().lower()
                    ext = CONTENT_TYPE_EXT.get(mime, ".html")
                    if not os.path.splitext(local_path)[1]:
                        local_path += ext
                elif local_path.endswith("/"):
                    local_path += "index.html"
                else:
                    local_path += ".html"

            self.url_to_local[url] = local_path
            return local_path
        finally:
            if lock:
                lock.release()

    # ------------------------------------------------------------------
    # Path-traversal guard (delegates to security module)
    # ------------------------------------------------------------------

    def _safe_path(self, local_path: str, output_dir: str) -> str:
        """Wraps :func:`security.safe_path` for convenience."""
        from .security import safe_path as _safe

        return _safe(local_path, output_dir)
