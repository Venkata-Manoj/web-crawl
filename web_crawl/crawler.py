"""WebsiteCloner — main orchestration class for Website Cloner v2.

This module re-exports the same ``WebsiteCloner`` class that v1 users
import from ``cloner.py``, along with the module-level convenience
functions ``clone_website_job``, ``clone_website``, and the CLI entry
point ``main``.
"""

import argparse
import logging
import os
import threading
from collections import deque
from typing import Dict, Optional, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import urllib.robotparser

from .config import PLAYWRIGHT_AVAILABLE
from .rate_limiter import DomainRateLimiter
from .rewriter import URLRewriter
from .storage import Storage
from .fetcher import HTTPFetcher, PlaywrightFetcher, ParallelFetcher
from .processor import HTMLProcessor, CSSProcessor
from .security import is_private_ip as _security_is_private_ip

logger = logging.getLogger(__name__)


# ======================================================================
# Main orchestration class
# ======================================================================


class WebsiteCloner:
    """Core engine for cloning websites — exact same API as v1.

    Parameters
    ----------
    seed_url : str
        The starting URL for the crawl.
    output_dir : str
        Directory to write the cloned site into (default ``"cloned_sites"``).
    max_pages : int
        Maximum number of HTML pages to clone.
    render_js : bool
        Whether to use Playwright for JS rendering.
    follow_domains : bool
        When True, follow links to any domain (default: same-domain only).
    delay : float
        Seconds to wait between HTTP requests.
    timeout : int
        Request timeout in seconds.
    max_retries : int
        Number of times to retry a failed request.
    scroll_depth : int
        How many scroll iterations to perform in JS mode.
    wait_ms : int
        Extra wait (ms) after scroll in JS mode.
    max_workers : int
        Thread pool size for parallel asset downloads.
    """

    def __init__(
        self,
        seed_url: str,
        output_dir: str = "cloned_sites",
        max_pages: int = 100,
        render_js: bool = False,
        follow_domains: bool = False,
        delay: float = 0,
        timeout: int = 30,
        max_retries: int = 3,
        scroll_depth: int = 5,
        wait_ms: int = 2000,
        max_workers: int = 4,
    ):
        # --- Store all parameters --------------------------------------------
        self.seed_url = seed_url
        self.output_dir = output_dir
        self.max_pages = max_pages
        self.render_js = render_js
        self.follow_domains = follow_domains
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.scroll_depth = scroll_depth
        self.wait_ms = wait_ms
        self.max_workers = max_workers

        # --- Domain info ------------------------------------------------------
        parsed = urlparse(self.seed_url)
        self.start_domain = parsed.netloc
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"

        # --- Shared crawl state ----------------------------------------------
        self.url_to_local: Dict[str, str] = {}
        self.visited: Set[str] = set()
        self.queue: deque = deque()
        self.assets_downloaded: Set[str] = set()
        self._assets_lock = threading.Lock()
        self._etags: dict[str, str] = {}
        self._last_modified: dict[str, str] = {}
        self._crawl_lock = threading.RLock()
        self._rate_limiter = DomainRateLimiter()

        # --- Shared requests session -----------------------------------------
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;" "q=0.9,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.5",
            }
        )

        # ---- Sub-module instances -------------------------------------------
        self.rewriter = URLRewriter(seed_url, lock=self._crawl_lock)
        self.storage = Storage()
        self.http_fetcher = HTTPFetcher(
            session=self.session,
            delay=self.delay,
            timeout=self.timeout,
            max_retries=self.max_retries,
            assets_downloaded=self.assets_downloaded,
            etags=self._etags,
            last_modified=self._last_modified,
            assets_lock=self._assets_lock,
            rate_limiter=self._rate_limiter,
        )
        self.pw_fetcher = PlaywrightFetcher(
            timeout=self.timeout,
            scroll_depth=self.scroll_depth,
            wait_ms=self.wait_ms,
        )
        self.parallel_fetcher = ParallelFetcher(max_workers=self.max_workers)
        self.css_processor = CSSProcessor(
            rewriter=self.rewriter,
            download_asset_fn=self._download_asset,
            output_dir=self.output_dir,
        )
        self.html_processor = HTMLProcessor(
            rewriter=self.rewriter,
            download_asset_fn=self._download_asset,
            process_css_fn=self._process_css,
            output_dir=self.output_dir,
            max_workers=self.max_workers,
            assets_downloaded=self.assets_downloaded,
            visited=self.visited,
            queue=self.queue,
            follow_domains=self.follow_domains,
            start_domain=self.start_domain,
            parallel_fetcher=self.parallel_fetcher,
            crawl_lock=self._crawl_lock,
        )

    # ======================================================================
    # Delegate methods — same names as v1 for backward compat / test mocking
    # ======================================================================

    # -- URL rewriting --------------------------------------------------------

    def _normalize_url(self, url: str) -> str:
        """Normalize URL by removing fragment, query, and trailing slash."""
        return self.rewriter._normalize_url(url)

    def _is_same_domain(self, url: str) -> bool:
        """Check if URL belongs to the start domain."""
        return self.rewriter._is_same_domain(url)

    def _is_html_link(self, url: str) -> bool:
        """Check if URL looks like an HTML page (not a binary file)."""
        return self.rewriter._is_html_link(url)

    def _local_path_for(self, url: str, content_type: Optional[str] = None) -> str:
        """Map URL to local file path."""
        return self.rewriter._local_path_for(url, content_type)

    def _safe_path(self, local_path: str) -> str:
        """Sanitize a local path to prevent path traversal."""
        return self.rewriter._safe_path(local_path, self.output_dir)

    # -- Security -------------------------------------------------------------

    def _is_private_ip(self, url: str) -> bool:
        """Check if a URL resolves to a private or loopback IP address."""
        return _security_is_private_ip(url)

    # -- Page fetching --------------------------------------------------------

    def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch a page using requests or Playwright."""
        if self._is_private_ip(url):
            logger.warning(f"Skipping page at private IP address: {url}")
            return None
        if self.render_js and PLAYWRIGHT_AVAILABLE:
            return self._fetch_with_playwright(url)
        return self._fetch_with_requests(url)

    def _fetch_with_requests(self, url: str) -> Optional[str]:
        """Fetch page using requests (static mode)."""
        return self.http_fetcher.fetch_with_requests(url)

    def _fetch_with_playwright(self, url: str) -> Optional[str]:
        """Fetch page using Playwright (JS render mode)."""
        return self.pw_fetcher.fetch_with_playwright(url)

    def _scroll_page(self, page) -> None:
        """Scroll to bottom to trigger lazy-loaded content."""
        self.pw_fetcher._scroll_page(page)

    def _wait_for_dynamic_content(self, page) -> None:
        """Wait for dynamic content (infinite scroll, animations, modals)."""
        self.pw_fetcher._wait_for_dynamic_content(page)

    def _intercept_api_data(self, page) -> None:
        """Click interactive buttons to trigger lazy API data."""
        self.pw_fetcher._intercept_api_data(page)

    def _get_playwright_browser(self):
        """Get or create the shared Playwright browser instance."""
        return self.pw_fetcher._get_playwright_browser()

    def _cleanup_playwright(self):
        """Clean up the shared Playwright browser and context."""
        self.pw_fetcher.cleanup()

    # -- Asset downloading ----------------------------------------------------

    def _download_asset(
        self, url: str, content_type: Optional[str] = None
    ) -> Optional[bytes]:
        """Download an asset and return its content."""
        return self.http_fetcher.download_asset(url, content_type)

    # -- Processing ----------------------------------------------------------

    def _process_css(self, css_content: str, base_url: str) -> str:
        """Process CSS content, download url() and @import references."""
        return self.css_processor.process_css(css_content, base_url)

    def _process_page(
        self, url: str, html: str, soup: Optional[BeautifulSoup] = None
    ) -> tuple[str, list[str]]:
        """Process HTML page: extract assets, download them, rewrite URLs."""
        return self.html_processor.process_page(url, html, soup=soup)

    # ======================================================================
    # Methods that stay on WebsiteCloner (orchestration / BFS loop)
    # ======================================================================

    def _parse_sitemap_recursive(self, sitemap_url: str, depth: int = 0) -> list[str]:
        """Recursively parse a sitemap or sitemap index, returning page URLs."""
        if depth > 3:
            return []
        try:
            resp = self.session.get(sitemap_url, timeout=self.timeout)
            if resp.status_code != 200 or "xml" not in resp.headers.get(
                "Content-Type", ""
            ):
                return []
            soup = BeautifulSoup(resp.content, "xml")

            sitemap_children = soup.find_all("sitemap")
            if sitemap_children:
                urls = []
                for sitemap_tag in sitemap_children:
                    loc = sitemap_tag.find("loc")
                    if loc and loc.get_text(strip=True):
                        urls.extend(
                            self._parse_sitemap_recursive(
                                loc.get_text(strip=True), depth + 1
                            )
                        )
                return urls

            urls = []
            for url_tag in soup.find_all("url"):
                loc = url_tag.find("loc")
                if loc and loc.get_text(strip=True):
                    urls.append(loc.get_text(strip=True))
            return urls

        except Exception as e:
            logger.debug(f"Failed to parse sitemap {sitemap_url}: {e}")
            return []

    def clone(self, progress_callback=None) -> str:
        """Main entry point: clone the website starting from seed_url.

        Parameters
        ----------
        progress_callback : callable or None
            Signature ``(pages_cloned, max_pages, current_url)``.
            Called after each page is saved so callers (e.g. Flask UI)
            can report progress live.

        Returns
        -------
        str
            Path to the output directory.
        """
        os.makedirs(self.output_dir, exist_ok=True)

        seed_normalized = self._normalize_url(self.seed_url)
        self._seed_normalized = seed_normalized
        self.queue.append(seed_normalized)
        self.visited.add(seed_normalized)

        pages_cloned = 0

        logger.info(f"Starting clone of {self.seed_url}")
        logger.info(f"Output directory: {self.output_dir}")
        logger.info(f"Max pages: {self.max_pages}, JS render: {self.render_js}")

        # Discover sitemap.xml for additional crawl seeds
        sitemap_url = urljoin(self.base_url, "/sitemap.xml")
        sitemap_urls = self._parse_sitemap_recursive(sitemap_url)
        for url_text in sitemap_urls:
            norm = self._normalize_url(url_text)
            if norm not in self.visited:
                self.visited.add(norm)
                self.queue.append(norm)
        if sitemap_urls:
            logger.info(f"Discovered {len(sitemap_urls)} URLs from sitemap")

        # Check robots.txt for disallowed paths
        self._rp = urllib.robotparser.RobotFileParser()
        self._rp.set_url(urljoin(self.base_url, "/robots.txt"))
        try:
            self._rp.read()
            logger.info(f"Parsed robots.txt for {self.base_url}")
        except Exception:
            self._rp = None
            logger.debug("No robots.txt found")

        while self.queue and pages_cloned < self.max_pages:
            current_url = self.queue.popleft()

            if (
                self._rp is not None
                and current_url != self._seed_normalized
                and not self._rp.can_fetch("*", current_url)
            ):
                logger.info(f"  Skipping (disallowed by robots.txt): {current_url}")
                continue

            logger.info(
                f"[{pages_cloned + 1}/{self.max_pages}] " f"Fetching: {current_url}"
            )
            html = self._fetch_page(current_url)

            if html is None:
                continue

            soup = BeautifulSoup(html, "lxml")
            processed_html, page_links = self._process_page(
                current_url, html, soup=soup
            )

            local_path = self._local_path_for(current_url)
            local_path = self._safe_path(local_path)
            full_path = os.path.join(self.output_dir, local_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(processed_html)

            pages_cloned += 1

            if progress_callback:
                progress_callback(pages_cloned, self.max_pages, current_url)

            for abs_href in page_links:
                norm_href = self._normalize_url(abs_href)
                if norm_href not in self.visited:
                    self.visited.add(norm_href)
                    self.queue.append(norm_href)

            logger.info(
                f"  Cloned: {local_path} "
                f"(queue: {len(self.queue)}, visited: {len(self.visited)})"
            )

        logger.info(f"Clone complete: {pages_cloned} pages cloned to {self.output_dir}")
        self._cleanup_playwright()
        return self.output_dir


# ======================================================================
# Module-level convenience functions
# ======================================================================


def clone_website_job(config: dict, progress_callback=None) -> str:
    """Run a clone job from a ``config`` dict.

    This is the entry point used by ``app.py`` (Flask web UI).
    """
    cloner = WebsiteCloner(
        seed_url=config["url"],
        output_dir=config["output"],
        max_pages=config.get("max_pages", 100),
        render_js=config.get("render_js", False),
        follow_domains=config.get("follow_domains", False),
        delay=config.get("delay", 0.2),
        timeout=config.get("timeout", 30),
        max_retries=config.get("max_retries", 3),
        scroll_depth=config.get("scroll_depth", 5),
        wait_ms=config.get("wait_ms", 2000),
    )
    return cloner.clone(progress_callback=progress_callback)


def clone_website(
    url: str,
    output_dir: str = "cloned_sites",
    max_pages: int = 100,
    render_js: bool = False,
    follow_domains: bool = False,
    delay: float = 0.2,
    progress_callback=None,
    scroll_depth: int = 5,
    wait_ms: int = 2000,
) -> str:
    """Convenience function to clone a website with a single call."""
    config = {
        "url": url,
        "output": output_dir,
        "max_pages": max_pages,
        "render_js": render_js,
        "follow_domains": follow_domains,
        "delay": delay,
        "scroll_depth": scroll_depth,
        "wait_ms": wait_ms,
    }
    return clone_website_job(config, progress_callback=progress_callback)


# ======================================================================
# CLI entry point
# ======================================================================


def main():
    """Parse CLI arguments and run a clone."""
    parser = argparse.ArgumentParser(
        description="Clone a website for offline viewing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python cloner.py https://example.com -o mysite -n 50
  python cloner.py https://example.com --js
  python cloner.py https://example.com --all-domains --delay 0.5
        """,
    )
    parser.add_argument("url", help="Seed URL to start cloning from")
    parser.add_argument(
        "-o",
        "--output",
        default="cloned_sites",
        help="Output directory (default: cloned_sites)",
    )
    parser.add_argument(
        "-n",
        "--max-pages",
        type=int,
        default=100,
        help="Maximum pages to clone (default: 100)",
    )
    parser.add_argument(
        "--js",
        action="store_true",
        help="Enable JavaScript rendering (requires Playwright)",
    )
    parser.add_argument(
        "--all-domains",
        action="store_true",
        help="Follow links to other domains",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Delay between requests in seconds (default: 0.2)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--scroll-depth",
        type=int,
        default=5,
        help="Max scroll iterations for lazy content (default: 5, JS mode only)",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=2000,
        help="Extra wait time in ms after scroll (default: 2000, JS mode only)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.js and not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not installed. Falling back to static mode.")
        logger.info(
            "To enable JS rendering, run: "
            "pip install playwright && playwright install chromium"
        )
        args.js = False

    def progress(cloned, total, url):
        print(f"  Progress: {cloned}/{total} pages cloned")

    output = clone_website(
        url=args.url,
        output_dir=args.output,
        max_pages=args.max_pages,
        render_js=args.js,
        follow_domains=args.all_domains,
        delay=args.delay,
        progress_callback=progress,
        scroll_depth=args.scroll_depth,
        wait_ms=args.wait_ms,
    )

    print(f"\nDone! Cloned site saved to: {output}")
