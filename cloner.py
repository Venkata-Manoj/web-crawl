#!/usr/bin/env python3
"""
Website Cloner - Downloads entire websites for offline viewing.

Pure Python automation — no API keys, no AI models.
Two delivery surfaces share one engine: CLI and Flask web app.
"""

import argparse
import hashlib
import ipaddress
import logging
import os
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from collections import deque
from typing import Dict, Optional, Set
import urllib.robotparser
from urllib.parse import unquote_plus, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

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
    ".html", ".htm", ".css", ".js", ".json", ".png", ".jpg", ".jpeg",
    ".gif", ".webp", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".otf",
    ".eot", ".mp3", ".ogg", ".mp4", ".webm", ".pdf", ".zip", ".xml",
    ".php", ".asp", ".aspx",
}

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

CSS_URL_RE = re.compile(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)')
CSS_IMPORT_RE = re.compile(r'@import\s+["\']([^"\']+)["\']')


class WebsiteCloner:
    """Core engine for cloning websites."""

    def __init__(
        self,
        seed_url: str,
        output_dir: str = "cloned_sites",
        max_pages: int = 100,
        render_js: bool = False,
        follow_domains: bool = False,
        delay: float = 0.2,
        timeout: int = 30,
        max_retries: int = 3,
        scroll_depth: int = 5,
        wait_ms: int = 2000,
        max_workers: int = 10,
    ):
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

        parsed = urlparse(self.seed_url)
        self.start_domain = parsed.netloc
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"

        self.url_to_local: Dict[str, str] = {}
        self.visited: Set[str] = set()
        self.queue: deque = deque()
        self.assets_downloaded: Set[str] = set()
        self._assets_lock = threading.Lock()
        self._etags: dict[str, str] = {}
        self._last_modified: dict[str, str] = {}

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.5",
        })

        # Shared Playwright browser (lazily initialized, reused across fetches)
        self._pw_playwright = None
        self._pw_browser = None

    def _normalize_url(self, url: str) -> str:
        """Normalize URL by removing fragment, query, and trailing slash."""
        parsed = urlparse(url)
        normalized = urlunparse(parsed._replace(
            fragment="",
            path=parsed.path.rstrip("/") or "/"
        ))
        return normalized

    def _is_same_domain(self, url: str) -> bool:
        """Check if URL belongs to the start domain."""
        return urlparse(url).netloc == self.start_domain

    def _is_html_link(self, url: str) -> bool:
        """Check if URL looks like an HTML page (not a binary file).

        Uses urlparse to extract the clean path before checking the extension,
        ensuring query strings (?v=2) and fragments are never passed to
        os.path.splitext (which does not understand URL structure).
        """
        parsed = urlparse(url)
        path = parsed.path.lower()
        if not path or path == "/":
            return True
        ext = os.path.splitext(path)[1]
        if ext in KNOWN_EXTS and ext not in (".html", ".htm", ".php", ".asp", ".aspx"):
            return False
        return True

    def _local_path_for(self, url: str, content_type: Optional[str] = None) -> str:
        """Map URL to local file path (centralized, deterministic).

        Handles URL-encoded query strings (%3F in path → real query separator),
        so filenames stay clean even when upstream CSS uses url('font.woff?v=...').
        """
        if url in self.url_to_local:
            return self.url_to_local[url]

        parsed = urlparse(url)
        # Unquote the path first to handle %3F (encoded '?') that some CDNs
        # embed for cache-busting — urlparse treats it as part of the path,
        # which makes splitext see a bogus extension like .woff%3Fv=3.2.1
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

    def _safe_path(self, local_path: str) -> str:
        """Sanitize a local path to prevent path traversal.

        Resolves '..' sequences and ensures the resulting path
        stays within self.output_dir. If traversal is detected,
        the path is hashed to a safe name.
        """
        full_path = os.path.abspath(os.path.join(self.output_dir, local_path))
        output_dir_abs = os.path.abspath(self.output_dir)
        if os.path.commonpath([full_path, output_dir_abs]) != output_dir_abs:
            ext = os.path.splitext(local_path)[1]
            return hashlib.md5(local_path.encode()).hexdigest()[:16] + ext
        return os.path.relpath(full_path, self.output_dir)

    def _is_private_ip(self, url: str) -> bool:
        """Check if a URL resolves to a private or loopback IP address."""
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        try:
            ip = socket.gethostbyname(hostname)
            addr = ipaddress.ip_address(ip)
            return addr.is_private or addr.is_loopback or addr.is_link_local
        except (socket.gaierror, ValueError):
            return False

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
        for attempt in range(self.max_retries):
            try:
                time.sleep(self.delay)
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" in content_type or "text/plain" in content_type:
                    return resp.text
                return None
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt+1}/{self.max_retries} failed for {url}: {e}")
                if attempt == self.max_retries - 1:
                    logger.error(f"Failed to fetch {url} after {self.max_retries} attempts")
                    return None
                time.sleep(2 ** attempt)
        return None

    def _get_playwright_browser(self):
        """Get or create the shared Playwright browser instance."""
        if self._pw_browser is not None:
            return self._pw_browser
        try:
            self._pw_playwright = sync_playwright().start()
            self._pw_browser = self._pw_playwright.chromium.launch(headless=True)
            return self._pw_browser
        except Exception as e:
            logger.error(f"Failed to launch Playwright browser: {e}")
            raise

    def _fetch_with_playwright(self, url: str) -> Optional[str]:
        """Fetch page using Playwright (JS render mode).
        Tries networkidle first, falls back to domcontentloaded on timeout
        (handles SPAs with persistent connections).
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
                    page.goto(url, wait_until="networkidle",
                              timeout=min(self.timeout * 1000, 15000))
                except Exception:
                    logger.debug(
                        f"  networkidle timeout for {url}, "
                        "falling back to domcontentloaded"
                    )
                    page.goto(url, wait_until="domcontentloaded",
                              timeout=self.timeout * 1000)

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

    def _scroll_page(self, page) -> None:
        """Scroll to bottom to trigger lazy-loaded content."""
        for i in range(self.scroll_depth):
            prev_height = page.evaluate("document.body.scrollHeight")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == prev_height:
                break
            logger.debug(f"  Scroll {i+1}: height {prev_height} -> {new_height}")

    def _wait_for_dynamic_content(self, page) -> None:
        """Wait for dynamic content (infinite scroll, animations, modals)."""
        page.wait_for_timeout(self.wait_ms)

    def _intercept_api_data(self, page) -> None:
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

    def _download_asset(self, url: str, content_type: Optional[str] = None) -> Optional[bytes]:
        """Download an asset and return its content."""
        if url in self.assets_downloaded:
            return None
        if url.startswith("data:"):
            return None
        if self._is_private_ip(url):
            logger.warning(f"Skipping asset at private IP address: {url}")
            return None

        for attempt in range(self.max_retries):
            try:
                headers = {}
                if url in self._etags:
                    headers["If-None-Match"] = self._etags[url]
                elif url in self._last_modified:
                    headers["If-Modified-Since"] = self._last_modified[url]

                resp = self.session.get(url, timeout=self.timeout, stream=True, headers=headers)
                if resp.status_code == 304:
                    self.assets_downloaded.add(url)
                    return None
                resp.raise_for_status()

                if not content_type:
                    content_type = resp.headers.get("Content-Type", "")

                content = resp.content
                etag = resp.headers.get("ETag")
                if etag:
                    self._etags[url] = etag
                lm = resp.headers.get("Last-Modified")
                if lm:
                    self._last_modified[url] = lm
                self.assets_downloaded.add(url)
                return content
            except requests.RequestException as e:
                logger.warning(
                    f"Asset download attempt {attempt+1}/{self.max_retries} "
                    f"failed for {url}: {e}"
                )
                if attempt == self.max_retries - 1:
                    logger.error(
                        f"Failed to download asset {url} after "
                        f"{self.max_retries} attempts"
                    )
                    return None
                time.sleep(2 ** attempt)
        return None

    def _process_css(self, css_content: str, base_url: str) -> str:
        """Process CSS content, download url() and @import references."""
        def replace_url(match):
            url = match.group(1).strip()
            if url.startswith("data:"):
                return match.group(0)

            abs_url = urljoin(base_url, url)
            local_path = self._local_path_for(abs_url)
            local_path = self._safe_path(local_path)
            full_path = os.path.join(self.output_dir, local_path)

            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            content = self._download_asset(abs_url)
            if content:
                with open(full_path, "wb") as f:
                    f.write(content)

            return f'url("{local_path}")'

        def replace_import(match):
            url = match.group(1).strip()
            abs_url = urljoin(base_url, url)
            local_path = self._local_path_for(abs_url)
            local_path = self._safe_path(local_path)
            full_path = os.path.join(self.output_dir, local_path)

            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            content = self._download_asset(abs_url)
            if content:
                with open(full_path, "wb") as f:
                    f.write(content)

            return f'@import "{local_path}"'

        css_content = CSS_URL_RE.sub(replace_url, css_content)
        css_content = CSS_IMPORT_RE.sub(replace_import, css_content)
        return css_content

    def _process_page(self, url: str, html: str, soup: Optional[BeautifulSoup] = None) -> tuple[str, list[str]]:
        """Process HTML page: extract assets, download them, rewrite URLs.

        Returns (processed_html, page_links) so the caller can avoid
        a second BeautifulSoup parse for link discovery.
        """
        if soup is None:
            soup = BeautifulSoup(html, "lxml")

        # Extract page links BEFORE modifying soup
        page_links = []
        for tag in soup.find_all("a"):
            href = tag.get("href")
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                abs_href = urljoin(url, href)
                if self._is_same_domain(abs_href) or self.follow_domains:
                    if self._is_html_link(abs_href):
                        page_links.append(abs_href)

        # Phase 1: collect all asset download tasks
        # Each task: (abs_url, content_type, local_path, tag, attr, tag_name, is_stylesheet)
        download_tasks = []
        # srcset entries need special handling: (tag, attr, [(tokens, url, local_path), ...])
        srcset_info = []

        for tag_name, attrs in ASSET_ATTRS.items():
            for tag in soup.find_all(tag_name):
                for attr in attrs:
                    value = tag.get(attr)
                    if not value or value.startswith("data:"):
                        continue

                    if attr == "srcset":
                        parts = value.split(",")
                        entries = []
                        for part in parts:
                            tokens = part.strip().split()
                            if tokens and not tokens[0].startswith("data:"):
                                img_url = urljoin(url, tokens[0])
                                local_path = self._local_path_for(img_url)
                                local_path = self._safe_path(local_path)
                                download_tasks.append(
                                    (img_url, None, local_path, None, None, None, False)
                                )
                                entries.append((tokens, img_url, local_path))
                            else:
                                entries.append((tokens, None, None))
                        srcset_info.append((tag, attr, entries))
                        continue

                    abs_url = urljoin(url, value)

                    # Determine content type and filter non-asset <link> elements
                    if tag_name == "link":
                        rel = tag.get("rel", [])
                        if isinstance(rel, str):
                            rel = [rel]
                        asset_rels = {
                            "stylesheet", "icon", "shortcut icon",
                            "apple-touch-icon", "apple-touch-icon-precomposed",
                            "preload", "prefetch", "dns-prefetch",
                        }
                        if not asset_rels.intersection(set(rel)):
                            continue
                        if "stylesheet" in rel:
                            content_type = "text/css"
                        elif "icon" in rel or "shortcut icon" in rel:
                            content_type = "image/x-icon"
                        else:
                            content_type = None
                    elif tag_name == "script":
                        content_type = "application/javascript"
                    elif tag_name in ("img", "video", "audio", "source", "input"):
                        content_type = None
                    else:
                        content_type = None

                    local_path = self._local_path_for(abs_url, content_type)
                    local_path = self._safe_path(local_path)
                    is_stylesheet = tag_name == "link" and "stylesheet" in tag.get("rel", [])
                    download_tasks.append(
                        (abs_url, content_type, local_path, tag, attr, tag_name, is_stylesheet)
                    )

        # Phase 2: download all unique assets in parallel
        downloaded = {}
        seen = set()
        unique = []
        for item in download_tasks:
            abs_url = item[0]
            if abs_url in self.assets_downloaded or abs_url.startswith("data:") or abs_url in seen:
                continue
            seen.add(abs_url)
            unique.append((abs_url, item[1]))

        if unique:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_map = {}
                for abs_url, ct in unique:
                    fut = executor.submit(self._download_asset, abs_url, ct)
                    future_map[fut] = abs_url
                for fut in as_completed(future_map):
                    abs_url = future_map[fut]
                    try:
                        content = fut.result()
                        if content:
                            downloaded[abs_url] = content
                    except Exception as e:
                        logger.warning(f"Asset download failed for {abs_url}: {e}")

        # Phase 3: save downloaded files and rewrite tag attributes
        for item in download_tasks:
            abs_url, content_type, local_path, tag, attr, tag_name, is_stylesheet = item
            content = downloaded.get(abs_url)
            if not content:
                if tag is not None and abs_url in self.assets_downloaded:
                    tag[attr] = local_path
                continue

            full_path = os.path.join(self.output_dir, local_path)
            dir_name = os.path.dirname(full_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

            if is_stylesheet:
                try:
                    css_text = content.decode("utf-8")
                except UnicodeDecodeError:
                    css_text = content.decode("latin-1")
                css_text = self._process_css(css_text, abs_url)
                content = css_text.encode("utf-8")

            with open(full_path, "wb") as f:
                f.write(content)

            if tag is not None:
                tag[attr] = local_path

        # Phase 4: reconstruct srcset attributes
        for tag, attr, entries in srcset_info:
            new_parts = []
            for tokens, img_url, local_path in entries:
                if img_url and local_path:
                    tokens[0] = local_path
                new_parts.append(" ".join(tokens))
            tag[attr] = ", ".join(new_parts)

        # Process <style> tags
        for style_tag in soup.find_all("style"):
            if style_tag.string:
                style_tag.string = self._process_css(style_tag.string, url)

        # Rewrite <a> links for offline viewing
        for tag in soup.find_all("a"):
            href = tag.get("href")
            if href:
                abs_href = urljoin(url, href)
                if self._is_same_domain(abs_href) or self.follow_domains:
                    if self._is_html_link(abs_href):
                        local_path = self._local_path_for(abs_href)
                        local_path = self._safe_path(local_path)
                        tag["href"] = local_path

        # Strip SRI integrity hashes (no longer valid after local download)
        for tag in soup.find_all(["script", "link", "style"]):
            tag.attrs.pop("integrity", None)
            tag.attrs.pop("crossorigin", None)

        # Handle <meta http-equiv="refresh"> redirects
        meta_refresh = soup.find("meta", attrs={"http-equiv": lambda v: v and v.lower() == "refresh"})
        if meta_refresh and meta_refresh.get("content"):
            match = re.search(r'url\s*=\s*["\']?([^"\'\s>]+)', meta_refresh["content"], re.IGNORECASE)
            if match:
                redirect_url = urljoin(url, match.group(1))
                # Add to crawl queue if not visited
                norm = self._normalize_url(redirect_url)
                if norm not in self.visited:
                    self.visited.add(norm)
                    self.queue.append(norm)

        return str(soup), page_links

    def _cleanup_playwright(self):
        """Clean up the shared Playwright browser and context."""
        try:
            if self._pw_browser:
                self._pw_browser.close()
                self._pw_browser = None
            if self._pw_playwright:
                self._pw_playwright.stop()
                self._pw_playwright = None
        except Exception as e:
            logger.warning(f"Playwright cleanup failed: {e}")

    def _parse_sitemap_recursive(self, sitemap_url: str, depth: int = 0) -> list[str]:
        """Recursively parse a sitemap or sitemap index, returning page URLs."""
        if depth > 3:  # Prevent infinite recursion
            return []
        try:
            resp = self.session.get(sitemap_url, timeout=self.timeout)
            if resp.status_code != 200 or "xml" not in resp.headers.get("Content-Type", ""):
                return []
            soup = BeautifulSoup(resp.content, "xml")

            # Check if this is a sitemap index (contains <sitemap> children)
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

            # Regular sitemap — extract page URLs from <url><loc> elements
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
        """Main entry point: clone the website starting from seed_url."""
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

            if self._rp is not None and current_url != self._seed_normalized \
                    and not self._rp.can_fetch("*", current_url):
                logger.info(f"  Skipping (disallowed by robots.txt): {current_url}")
                continue

            logger.info(f"[{pages_cloned+1}/{self.max_pages}] Fetching: {current_url}")
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


def clone_website_job(config: dict, progress_callback=None) -> str:
    """Run a clone job from a config dict (decouples app.py from WebsiteCloner internals)."""
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
    """Convenience function to clone a website."""
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


def main():
    parser = argparse.ArgumentParser(
        description="Clone a website for offline viewing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cloner.py https://example.com -o mysite -n 50
  python cloner.py https://example.com --js
  python cloner.py https://example.com --all-domains --delay 0.5
        """,
    )
    parser.add_argument(
        "url", help="Seed URL to start cloning from"
    )
    parser.add_argument(
        "-o", "--output", default="cloned_sites",
        help="Output directory (default: cloned_sites)"
    )
    parser.add_argument(
        "-n", "--max-pages", type=int, default=100,
        help="Maximum pages to clone (default: 100)"
    )
    parser.add_argument(
        "--js", action="store_true",
        help="Enable JavaScript rendering (requires Playwright)"
    )
    parser.add_argument(
        "--all-domains", action="store_true",
        help="Follow links to other domains"
    )
    parser.add_argument(
        "--delay", type=float, default=0.2,
        help="Delay between requests in seconds (default: 0.2)"
    )
    parser.add_argument(
        "--timeout", type=int, default=30,
        help="Request timeout in seconds (default: 30)"
    )
    parser.add_argument(
        "--scroll-depth", type=int, default=5,
        help="Max scroll iterations for lazy content (default: 5, JS mode only)"
    )
    parser.add_argument(
        "--wait-ms", type=int, default=2000,
        help="Extra wait time in ms after scroll (default: 2000, JS mode only)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.js and not PLAYWRIGHT_AVAILABLE:
        logger.warning(
            "Playwright not installed. Falling back to static mode."
        )
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


if __name__ == "__main__":
    main()
