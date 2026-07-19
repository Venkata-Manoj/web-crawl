"""HTML / CSS processing for Website Cloner v2.

Extracts assets from HTML, rewrites URLs for offline viewing, and
processes CSS ``url()`` and ``@import`` references.
"""

import logging
import os
import re
import threading
from typing import Callable, Optional, Set
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .config import ASSET_ATTRS, CSS_URL_RE, CSS_IMPORT_RE

logger = logging.getLogger(__name__)


# ======================================================================
# CSSProcessor
# ======================================================================


class CSSProcessor:
    """Rewrite CSS ``url()`` and ``@import`` references for local paths.

    For each referenced URL the processor:
      1. Resolves it to an absolute URL.
      2. Maps it to a local path via the shared URLRewriter.
      3. Downloads the asset (if not already cached).
      4. Saves it to the output directory.
      5. Substitutes the local path in the CSS.
    """

    def __init__(
        self,
        rewriter: "URLRewriter",  # noqa: F821 — forward-ref, resolved at runtime
        download_asset_fn: Callable,
        output_dir: str,
    ):
        self.rewriter = rewriter
        self._download_asset = download_asset_fn
        self.output_dir = output_dir

    def process_css(self, css_content: str, base_url: str) -> str:
        """Download CSS-referenced assets and rewrite paths to local.

        Returns the updated CSS text with ``url(...)`` and ``@import ...``
        pointing at relative local paths.
        """

        def replace_url(match):
            url = match.group(1).strip()
            if url.startswith("data:"):
                return match.group(0)

            abs_url = urljoin(base_url, url)
            local_path = self.rewriter._local_path_for(abs_url)
            local_path = self.rewriter._safe_path(local_path, self.output_dir)
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
            local_path = self.rewriter._local_path_for(abs_url)
            local_path = self.rewriter._safe_path(local_path, self.output_dir)
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


# ======================================================================
# HTMLProcessor
# ======================================================================


class HTMLProcessor:
    """Process a fetched HTML page: extract assets, download them, rewrite URLs.

    This class encapsulates the full ``_process_page`` logic from the
    original ``WebsiteCloner``.
    """

    def __init__(
        self,
        rewriter: "URLRewriter",  # noqa: F821
        download_asset_fn: Callable,
        process_css_fn: Callable,
        output_dir: str,
        max_workers: int,
        assets_downloaded: Set[str],
        visited: Set[str],
        queue: "deque",  # noqa: F821
        follow_domains: bool,
        start_domain: str,
        parallel_fetcher: "ParallelFetcher",  # noqa: F821
        crawl_lock: Optional["threading.RLock"] = None,  # noqa: F821
    ):
        self.rewriter = rewriter
        self._download_asset = download_asset_fn
        self._process_css = process_css_fn
        self.output_dir = output_dir
        self.max_workers = max_workers
        self._assets_downloaded = assets_downloaded
        self._visited = visited
        self._queue = queue
        self.follow_domains = follow_domains
        self.start_domain = start_domain
        self._parallel_fetcher = parallel_fetcher
        self._crawl_lock = crawl_lock

    # ------------------------------------------------------------------
    # Convenience accessors that delegate to the rewriter
    # ------------------------------------------------------------------

    def _is_same_domain(self, url: str) -> bool:
        return self.rewriter._is_same_domain(url)

    def _is_html_link(self, url: str) -> bool:
        return self.rewriter._is_html_link(url)

    def _normalize_url(self, url: str) -> str:
        return self.rewriter._normalize_url(url)

    def _local_path_for(self, url: str, content_type: Optional[str] = None) -> str:
        return self.rewriter._local_path_for(url, content_type)

    def _safe_path(self, local_path: str) -> str:
        return self.rewriter._safe_path(local_path, self.output_dir)

    # ------------------------------------------------------------------
    # Page processing (the big one)
    # ------------------------------------------------------------------

    def process_page(
        self, url: str, html: str, soup: Optional[BeautifulSoup] = None
    ) -> tuple[str, list[str]]:
        """Process HTML page: extract assets, download them, rewrite URLs.

        Returns
        -------
        (processed_html, page_links)
            The rewritten HTML string and a list of same-domain (or all-domain)
            HTML links discovered on the page.
        """
        if soup is None:
            soup = BeautifulSoup(html, "lxml")

        # ---- Extract page links BEFORE modifying soup ------------------------
        page_links = []
        for tag in soup.find_all("a"):
            href = tag.get("href")
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                abs_href = urljoin(url, href)
                if self._is_same_domain(abs_href) or self.follow_domains:
                    if self._is_html_link(abs_href):
                        page_links.append(abs_href)

        # ---- Phase 1: collect all asset download tasks ----------------------
        # Each task: (abs_url, content_type, local_path, tag, attr, tag_name, is_stylesheet)
        download_tasks = []
        # srcset entries need special handling
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

                    # Determine content type and filter non-asset <link>
                    if tag_name == "link":
                        rel = tag.get("rel", [])
                        if isinstance(rel, str):
                            rel = [rel]
                        asset_rels = {
                            "stylesheet",
                            "icon",
                            "shortcut icon",
                            "apple-touch-icon",
                            "apple-touch-icon-precomposed",
                            "preload",
                            "prefetch",
                            "dns-prefetch",
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
                    is_stylesheet = tag_name == "link" and "stylesheet" in tag.get(
                        "rel", []
                    )
                    download_tasks.append(
                        (
                            abs_url,
                            content_type,
                            local_path,
                            tag,
                            attr,
                            tag_name,
                            is_stylesheet,
                        )
                    )

        # ---- Phase 2: download all unique assets in parallel ----------------
        downloaded = {}
        seen = set()
        unique = []
        for item in download_tasks:
            abs_url = item[0]
            if (
                abs_url in self._assets_downloaded
                or abs_url.startswith("data:")
                or abs_url in seen
            ):
                continue
            seen.add(abs_url)
            unique.append((abs_url, item[1]))

        if unique:
            # Use ParallelFetcher for the actual parallel download
            downloaded = self._parallel_fetcher.fetch_all(unique, self._download_asset)

        # ---- Phase 3: save downloaded files and rewrite tag attributes -------
        for item in download_tasks:
            abs_url, content_type, local_path, tag, attr, tag_name, is_stylesheet = item
            content = downloaded.get(abs_url)
            if not content:
                if tag is not None and abs_url in self._assets_downloaded:
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

        # ---- Phase 4: reconstruct srcset attributes -------------------------
        for tag, attr, entries in srcset_info:
            new_parts = []
            for tokens, img_url, local_path in entries:
                if img_url and local_path:
                    tokens[0] = local_path
                new_parts.append(" ".join(tokens))
            tag[attr] = ", ".join(new_parts)

        # ---- Process <style> tags -------------------------------------------
        for style_tag in soup.find_all("style"):
            if style_tag.string:
                style_tag.string = self._process_css(style_tag.string, url)

        # ---- Rewrite <a> links for offline viewing --------------------------
        for tag in soup.find_all("a"):
            href = tag.get("href")
            if href:
                abs_href = urljoin(url, href)
                if self._is_same_domain(abs_href) or self.follow_domains:
                    if self._is_html_link(abs_href):
                        local_path = self._local_path_for(abs_href)
                        local_path = self._safe_path(local_path)
                        tag["href"] = local_path

        # ---- Strip SRI integrity hashes (no longer valid after download) ----
        for tag in soup.find_all(["script", "link", "style"]):
            tag.attrs.pop("integrity", None)
            tag.attrs.pop("crossorigin", None)

        # ---- Handle <meta http-equiv="refresh"> redirects -------------------
        meta_refresh = soup.find(
            "meta", attrs={"http-equiv": lambda v: v and v.lower() == "refresh"}
        )
        if meta_refresh and meta_refresh.get("content"):
            match = re.search(
                r'url\s*=\s*["\']?([^"\'\\s>]+)',
                meta_refresh["content"],
                re.IGNORECASE,
            )
            if match:
                redirect_url = urljoin(url, match.group(1))
                norm = self._normalize_url(redirect_url)
                lock = self._crawl_lock
                if lock:
                    lock.acquire()
                try:
                    if norm not in self._visited:
                        self._visited.add(norm)
                        self._queue.append(norm)
                finally:
                    if lock:
                        lock.release()

        return str(soup), page_links
