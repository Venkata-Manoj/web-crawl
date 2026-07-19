"""Configuration and constants for Website Cloner v2."""

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Playwright availability (optional dependency)
# ---------------------------------------------------------------------------

try:
    from playwright.sync_api import sync_playwright  # noqa: F401

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants — moved from cloner.py verbatim
# ---------------------------------------------------------------------------

CONTENT_TYPE_EXT = {
    "text/html": ".html",
    "text/css": ".css",
    "application/javascript": ".js",
    "text/javascript": ".js",
    "application/json": ".json",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
    "font/woff": ".woff",
    "font/woff2": ".woff2",
    "font/ttf": ".ttf",
    "font/otf": ".otf",
    "application/font-woff": ".woff",
    "application/font-woff2": ".woff2",
    "application/vnd.ms-fontobject": ".eot",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
}

KNOWN_EXTS = {
    ".html",
    ".htm",
    ".css",
    ".js",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".mp3",
    ".ogg",
    ".mp4",
    ".webm",
    ".pdf",
    ".zip",
    ".xml",
    ".php",
    ".asp",
    ".aspx",
}

MAX_ASSET_SIZE: int = 52428800  # 50 MB
MAX_TOTAL_BYTES: int = 2147483648  # 2 GB

ASSET_ATTRS = {
    "img": ["src", "srcset", "data-src", "data-srcset"],
    "script": ["src"],
    "link": ["href"],
    "video": ["src", "poster"],
    "audio": ["src"],
    "source": ["src", "srcset"],
    "input": ["src", "srcset"],
    "object": ["data"],
    "embed": ["src"],
    "iframe": ["src"],
    "frame": ["src"],
}

CSS_URL_RE = re.compile(r"url\(\s*[\"\']?([^\"\')]+)[\"\']?\s*\)")
CSS_IMPORT_RE = re.compile(r"@import\s+[\"\']([^\"\']+)[\"\']")


# ---------------------------------------------------------------------------
# Config dataclass — all WebsiteCloner.__init__ params
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Immutable-ish configuration for a WebsiteCloner instance."""

    seed_url: str
    output_dir: str = "cloned_sites"
    max_pages: int = 100
    render_js: bool = False
    follow_domains: bool = False
    delay: float = 0.2
    timeout: int = 30
    max_retries: int = 3
    scroll_depth: int = 5
    wait_ms: int = 2000
    max_workers: int = 4
