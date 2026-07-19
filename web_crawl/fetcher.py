"""HTTP / Playwright / parallel fetchers for Website Cloner v2."""

import datetime
import email.utils
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from .config import MAX_ASSET_SIZE, MAX_TOTAL_BYTES

logger = logging.getLogger(__name__)


# ======================================================================
# HTTPFetcher — synchronous requests-based downloading
# ======================================================================


class HTTPFetcher:
    """Fetch pages and download assets via ``requests``.

    Shares the same ``requests.Session``, rate-limiting delay, and
    caching headers (ETag / Last-Modified) with the rest of the cloner.
    """

    def __init__(
        self,
        session: requests.Session,
        delay: float = 0.2,
        timeout: int = 30,
        max_retries: int = 3,
        assets_downloaded: Optional[set] = None,
        etags: Optional[dict] = None,
        last_modified: Optional[dict] = None,
        assets_lock: Optional[threading.Lock] = None,
        max_asset_size: int = MAX_ASSET_SIZE,
        max_total_bytes: int = MAX_TOTAL_BYTES,
        rate_limiter: Optional["DomainRateLimiter"] = None,  # noqa: F821
    ):
        self.session = session
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_asset_size = max_asset_size
        self.max_total_bytes = max_total_bytes
        self.rate_limiter = rate_limiter
        self._assets_downloaded = (
            assets_downloaded if assets_downloaded is not None else set()
        )
        self._etags = etags if etags is not None else {}
        self._last_modified = last_modified if last_modified is not None else {}
        self._assets_lock = assets_lock if assets_lock is not None else threading.Lock()
        self._total_downloaded: int = 0

    # ------------------------------------------------------------------
    # Retry-After helper
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_retry_after(value: Optional[str]) -> Optional[float]:
        """Parse ``Retry-After`` header value (seconds-int or HTTP-date).

        Returns the number of seconds to wait, or ``None`` if unparseable.
        """
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            pass
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            now = datetime.datetime.now(datetime.timezone.utc)
            delta = parsed - now
            return max(0.0, delta.total_seconds())
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Page fetching
    # ------------------------------------------------------------------

    def fetch_with_requests(self, url: str) -> Optional[str]:
        """Fetch *url* with ``requests``, retrying on failure.

        Returns the response text (HTML) or ``None`` on persistent failure.
        """
        for attempt in range(self.max_retries):
            try:
                if self.rate_limiter:
                    self.rate_limiter.acquire(urlparse(url).netloc)
                time.sleep(self.delay)
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 429:
                    retry_after = self._parse_retry_after(
                        resp.headers.get("Retry-After")
                    )
                    if retry_after is not None:
                        time.sleep(retry_after)
                    else:
                        time.sleep(2**attempt)
                    continue
                resp.raise_for_status()
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" in content_type or "text/plain" in content_type:
                    return resp.text
                return None
            except requests.RequestException as e:
                logger.warning(
                    f"Attempt {attempt + 1}/{self.max_retries} failed for {url}: {e}"
                )
                if attempt == self.max_retries - 1:
                    logger.error(
                        f"Failed to fetch {url} after {self.max_retries} attempts"
                    )
                    return None
                time.sleep(2**attempt)
        return None

    # ------------------------------------------------------------------
    # Asset downloading (with caching headers)
    # ------------------------------------------------------------------

    def download_asset(
        self, url: str, content_type: Optional[str] = None
    ) -> Optional[bytes]:
        """Download a single asset (image, CSS, JS, font, …).

        Returns the raw bytes, or ``None`` if the asset was already
        downloaded or unreachable.

        Enforces per-asset (50 MB) and total (2 GB) size limits, streaming
        the response body in 64 KiB chunks.
        """
        if url in self._assets_downloaded:
            return None
        if url.startswith("data:"):
            return None

        for attempt in range(self.max_retries):
            try:
                if self.rate_limiter:
                    self.rate_limiter.acquire(urlparse(url).netloc)

                headers = {}
                if url in self._etags:
                    headers["If-None-Match"] = self._etags[url]
                elif url in self._last_modified:
                    headers["If-Modified-Since"] = self._last_modified[url]

                resp = self.session.get(
                    url, timeout=self.timeout, stream=True, headers=headers
                )
                if resp.status_code == 429:
                    retry_after = self._parse_retry_after(
                        resp.headers.get("Retry-After")
                    )
                    if retry_after is not None:
                        time.sleep(retry_after)
                    else:
                        time.sleep(2**attempt)
                    continue
                if resp.status_code == 304:
                    self._assets_downloaded.add(url)
                    return None
                resp.raise_for_status()

                if not content_type:
                    content_type = resp.headers.get("Content-Type", "")

                chunks = []
                asset_total = 0
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    asset_total += len(chunk)
                    if asset_total > self.max_asset_size:
                        logger.warning(
                            f"Asset {url} exceeds {self.max_asset_size} byte limit, "
                            "aborting download"
                        )
                        return None
                    chunks.append(chunk)

                if not chunks:
                    return None

                with self._assets_lock:
                    if self._total_downloaded + asset_total > self.max_total_bytes:
                        logger.warning(
                            f"Total download would exceed "
                            f"{self.max_total_bytes} byte limit"
                        )
                        return None
                    self._total_downloaded += asset_total

                content = b"".join(chunks)
                etag = resp.headers.get("ETag")
                if etag:
                    self._etags[url] = etag
                lm = resp.headers.get("Last-Modified")
                if lm:
                    self._last_modified[url] = lm
                self._assets_downloaded.add(url)
                return content
            except requests.RequestException as e:
                logger.warning(
                    f"Asset download attempt {attempt + 1}/{self.max_retries} "
                    f"failed for {url}: {e}"
                )
                if attempt == self.max_retries - 1:
                    logger.error(
                        f"Failed to download asset {url} after "
                        f"{self.max_retries} attempts"
                    )
                    return None
                time.sleep(2**attempt)
        return None


# ======================================================================
# PlaywrightFetcher — JS-rendered page fetching
# ======================================================================


class PlaywrightFetcher:
    """Fetch pages with JavaScript rendering via Playwright.

    The browser instance is lazily created and reused across fetches.
    Call :meth:`cleanup` when done to release system resources.
    """

    def __init__(
        self,
        timeout: int = 30,
        scroll_depth: int = 5,
        wait_ms: int = 2000,
    ):
        self.timeout = timeout
        self.scroll_depth = scroll_depth
        self.wait_ms = wait_ms

        # Lazy-initialised shared browser
        self._pw_playwright = None
        self._pw_browser = None

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    def _get_playwright_browser(self):
        """Get or create the shared Playwright Chromium instance."""
        if self._pw_browser is not None:
            return self._pw_browser
        try:
            from playwright.sync_api import sync_playwright

            self._pw_playwright = sync_playwright().start()
            self._pw_browser = self._pw_playwright.chromium.launch(headless=True)
            return self._pw_browser
        except Exception as e:
            logger.error(f"Failed to launch Playwright browser: {e}")
            raise

    def cleanup(self):
        """Close the shared Playwright browser and stop the driver."""
        try:
            if self._pw_browser:
                self._pw_browser.close()
                self._pw_browser = None
            if self._pw_playwright:
                self._pw_playwright.stop()
                self._pw_playwright = None
        except Exception as e:
            logger.warning(f"Playwright cleanup failed: {e}")

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def fetch_with_playwright(self, url: str) -> Optional[str]:
        """Fetch *url* with Playwright (full JS rendering).

        Tries ``networkidle`` first, falls back to ``domcontentloaded``
        on timeout (handles SPAs with persistent connections).
        """
        try:
            browser = self._get_playwright_browser()
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            try:
                try:
                    page.goto(
                        url,
                        wait_until="networkidle",
                        timeout=min(self.timeout * 1000, 15000),
                    )
                except Exception:
                    logger.debug(
                        f"  networkidle timeout for {url}, "
                        "falling back to domcontentloaded"
                    )
                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout * 1000,
                    )

                self._scroll_page(page)
                self._wait_for_dynamic_content(page)
                self._intercept_api_data(page)

                content = page.content()
                return content
            except Exception as e:
                logger.warning(f"Playwright fetch failed for {url}: {e}")
                return None
            finally:
                context.close()
        except Exception as e:
            logger.error(f"Playwright fetch failed for {url}: {e}")
            return None

    # ------------------------------------------------------------------
    # Dynamic content helpers
    # ------------------------------------------------------------------

    def _scroll_page(self, page) -> None:
        """Scroll to bottom repeatedly to trigger lazy-loaded content."""
        for i in range(self.scroll_depth):
            prev_height = page.evaluate("document.body.scrollHeight")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == prev_height:
                break
            logger.debug(f"  Scroll {i + 1}: height {prev_height} -> {new_height}")

    def _wait_for_dynamic_content(self, page) -> None:
        """Wait for dynamic content (infinite scroll, animations, modals)."""
        page.wait_for_timeout(self.wait_ms)

    def _intercept_api_data(self, page) -> None:
        """Click up to 5 interactive buttons to trigger lazy content."""
        max_buttons = 5
        click_delay = 500
        settle_delay = 1000
        try:
            buttons = page.query_selector_all(
                "button:not([disabled]), [role='button'], "
                "[data-toggle], [data-expand]"
            )
            clicked = 0
            original_url = page.url
            for btn in buttons[:max_buttons]:
                try:
                    if btn.is_visible():
                        btn.click()
                        page.wait_for_timeout(click_delay)
                        if page.url != original_url:
                            page.go_back()
                            page.wait_for_timeout(click_delay)
                        else:
                            clicked += 1
                except Exception:
                    pass
            if clicked:
                logger.debug(f"  Clicked {clicked} interactive elements")
                page.wait_for_timeout(settle_delay)
        except Exception:
            pass


# ======================================================================
# ParallelFetcher — multi-threaded asset downloader
# ======================================================================


class ParallelFetcher:
    """Download multiple assets concurrently via ``ThreadPoolExecutor``."""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers

    def fetch_all(
        self,
        items: List[Tuple],
        download_fn: Callable,
    ) -> Dict[str, bytes]:
        """Download several URLs in parallel.

        Parameters
        ----------
        items:
            List of ``(url, content_type)`` tuples.  The caller should
            pre-filter to unique URLs that have not been downloaded yet.
        download_fn:
            ``callable(url, content_type) -> Optional[bytes]``.  Typically
            :meth:`HTTPFetcher.download_asset`.

        Returns
        -------
        Dict[str, bytes]
            Mapping of *url* → *content bytes* for every successful download.
        """
        results: Dict[str, bytes] = {}
        if not items:
            return results

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_map = {}
            for url, ct in items:
                fut = executor.submit(download_fn, url, ct)
                future_map[fut] = url

            for fut in as_completed(future_map):
                url = future_map[fut]
                try:
                    content = fut.result()
                    if content:
                        results[url] = content
                except Exception as e:
                    logger.warning(f"Asset download failed for {url}: {e}")
        return results
