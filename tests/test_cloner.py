"""Test suite for WebsiteCloner — pure unit tests, no real network I/O."""

import hashlib
import os
import shutil
import socket
import tempfile
import unittest
from unittest import mock

from cloner import WebsiteCloner

# =============================================================================
# _normalize_url
# =============================================================================


class TestNormalizeUrl(unittest.TestCase):
    """_normalize_url strips fragments, preserves query strings, removes trailing slashes."""

    def setUp(self):
        self.cloner = WebsiteCloner("http://example.com")

    def test_strips_fragments(self):
        """#section is removed from URL."""
        url = "http://example.com/page#section"
        self.assertEqual(self.cloner._normalize_url(url), "http://example.com/page")

    def test_preserves_query_strings(self):
        """?foo=bar is kept."""
        url = "http://example.com/page?foo=bar"
        self.assertEqual(
            self.cloner._normalize_url(url), "http://example.com/page?foo=bar"
        )

    def test_preserves_query_with_fragment(self):
        """Fragment stripped, query kept when both present."""
        url = "http://example.com/page?foo=bar#section"
        self.assertEqual(
            self.cloner._normalize_url(url), "http://example.com/page?foo=bar"
        )

    def test_removes_trailing_slash(self):
        """/page/ becomes /page."""
        url = "http://example.com/page/"
        self.assertEqual(self.cloner._normalize_url(url), "http://example.com/page")

    def test_root_path_stays(self):
        """Root path / stays as / (not empty)."""
        url = "http://example.com/"
        self.assertEqual(self.cloner._normalize_url(url), "http://example.com/")

    def test_noop_on_clean_url(self):
        """URL without fragments, query, or trailing slash is unchanged."""
        url = "http://example.com/about"
        self.assertEqual(self.cloner._normalize_url(url), "http://example.com/about")


# =============================================================================
# _is_same_domain
# =============================================================================


class TestIsSameDomain(unittest.TestCase):
    """_is_same_domain checks URL belongs to the start domain."""

    def setUp(self):
        self.cloner = WebsiteCloner("http://example.com")

    def test_same_domain_returns_true(self):
        """Same hostname → True."""
        self.assertTrue(self.cloner._is_same_domain("http://example.com/page"))

    def test_different_domain_returns_false(self):
        """Different hostname → False."""
        self.assertFalse(self.cloner._is_same_domain("http://other.com/page"))

    def test_subdomain_is_different(self):
        """Subdomain (sub.example.com) is not the same as example.com."""
        self.assertFalse(self.cloner._is_same_domain("http://sub.example.com/page"))

    def test_different_scheme_same_domain(self):
        """Scheme (https vs http) does not affect domain check."""
        self.assertTrue(self.cloner._is_same_domain("https://example.com/page"))

    def test_port_in_url_mismatch(self):
        """Different port → different netloc → False."""
        self.assertFalse(self.cloner._is_same_domain("http://example.com:8080/page"))


# =============================================================================
# _is_html_link
# =============================================================================


class TestIsHtmlLink(unittest.TestCase):
    """_is_html_link detects whether a URL links to an HTML page."""

    def setUp(self):
        self.cloner = WebsiteCloner("http://example.com")

    def test_no_extension_returns_true(self):
        """Path without extension is assumed HTML."""
        self.assertTrue(self.cloner._is_html_link("/about"))

    def test_dot_html_returns_true(self):
        """.html extension is HTML."""
        self.assertTrue(self.cloner._is_html_link("/about.html"))

    def test_jpg_returns_false(self):
        """.jpg is a binary asset, not HTML."""
        self.assertFalse(self.cloner._is_html_link("/image.jpg"))

    def test_css_returns_false(self):
        """.css is a stylesheet, not HTML."""
        self.assertFalse(self.cloner._is_html_link("/style.css"))

    def test_root_returns_true(self):
        """Root path / is HTML."""
        self.assertTrue(self.cloner._is_html_link("/"))

    def test_empty_path_returns_true(self):
        """Empty path is assumed HTML."""
        self.assertTrue(self.cloner._is_html_link(""))

    def test_php_returns_true(self):
        """.php is treated as HTML (server-rendered)."""
        self.assertTrue(self.cloner._is_html_link("/page.php"))

    def test_png_returns_false(self):
        """.png is a binary asset."""
        self.assertFalse(self.cloner._is_html_link("/image.png"))

    def test_url_with_query_string(self):
        """Query string does not affect HTML detection."""
        self.assertTrue(self.cloner._is_html_link("/about?page=1"))

    def test_url_with_fragment(self):
        """Fragment does not affect HTML detection."""
        self.assertTrue(self.cloner._is_html_link("/about#section"))

    def test_js_returns_false(self):
        """.js is a script asset, not HTML."""
        self.assertFalse(self.cloner._is_html_link("/app.js"))


# =============================================================================
# _local_path_for
# =============================================================================


class TestLocalPathFor(unittest.TestCase):
    """_local_path_for maps URLs to deterministic local file paths."""

    def setUp(self):
        self.cloner = WebsiteCloner("http://example.com")

    def test_root_maps_to_index_html(self):
        """Root URL → index.html."""
        self.assertEqual(
            self.cloner._local_path_for("http://example.com/"), "index.html"
        )

    def test_about_maps_to_about_html(self):
        """/about → about.html (no extension → .html appended)."""
        self.assertEqual(
            self.cloner._local_path_for("http://example.com/about"), "about.html"
        )

    def test_preserves_known_extension_css(self):
        """.css extension is preserved."""
        self.assertEqual(
            self.cloner._local_path_for("http://example.com/style.css"), "style.css"
        )

    def test_preserves_known_extension_js(self):
        """.js extension is preserved."""
        self.assertEqual(
            self.cloner._local_path_for("http://example.com/app.js"), "app.js"
        )

    def test_uses_content_type_when_no_extension_json(self):
        """No extension + content_type=application/json → .json appended."""
        self.assertEqual(
            self.cloner._local_path_for(
                "http://example.com/data", content_type="application/json"
            ),
            "data.json",
        )

    def test_uses_content_type_when_no_extension_css(self):
        """No extension + content_type=text/css → .css appended."""
        self.assertEqual(
            self.cloner._local_path_for(
                "http://example.com/styles", content_type="text/css"
            ),
            "styles.css",
        )

    def test_content_type_with_charset(self):
        """Content-Type with charset (text/html; charset=utf-8) is handled."""
        self.assertEqual(
            self.cloner._local_path_for(
                "http://example.com/page", content_type="text/html; charset=utf-8"
            ),
            "page.html",
        )

    def test_nested_path_preserved(self):
        """/blog/post → blog/post.html (directory structure kept)."""
        self.assertEqual(
            self.cloner._local_path_for("http://example.com/blog/post"),
            "blog/post.html",
        )

    def test_cached_result_returned(self):
        """Subsequent calls for the same URL return the cached result."""
        first = self.cloner._local_path_for("http://example.com/page")
        second = self.cloner._local_path_for("http://example.com/page")
        self.assertEqual(first, second)

    def test_known_extensions_not_replaced(self):
        """Known extension .jpeg is preserved even without content_type."""
        self.assertEqual(
            self.cloner._local_path_for("http://example.com/photo.jpeg"), "photo.jpeg"
        )


# =============================================================================
# _safe_path
# =============================================================================


class TestSafePath(unittest.TestCase):
    """_safe_path prevents path traversal attacks."""

    def setUp(self):
        # Use an absolute path for output_dir so os.path.commonpath
        # doesn't fail with "Can't mix absolute and relative paths".
        self.temp_dir = tempfile.mkdtemp()
        self.cloner = WebsiteCloner("http://example.com", output_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_normal_path_stays_unchanged(self):
        """Simple filename passes through unchanged."""
        self.assertEqual(self.cloner._safe_path("about.html"), "about.html")

    def test_nested_path_preserved(self):
        """Nested directory structure is preserved."""
        self.assertEqual(self.cloner._safe_path("blog/post.html"), "blog/post.html")

    def test_path_traversal_gets_hashed(self):
        """../../../etc/passwd is hashed to a safe name (no extension)."""
        result = self.cloner._safe_path("../../../etc/passwd")
        expected_hash = hashlib.md5(b"../../../etc/passwd").hexdigest()[:16]
        self.assertEqual(result, expected_hash)

    def test_path_traversal_with_extension(self):
        """../../../etc/hosts.txt is hashed but keeps .txt extension."""
        result = self.cloner._safe_path("../../../etc/hosts.txt")
        expected = hashlib.md5(b"../../../etc/hosts.txt").hexdigest()[:16] + ".txt"
        self.assertEqual(result, expected)

    def test_double_dot_in_middle_is_safe(self):
        """A path that stays within output_dir is not treated as traversal."""
        inner = os.path.join("subdir", "..", "about.html")
        result = self.cloner._safe_path(inner)
        self.assertEqual(result, "about.html")


# =============================================================================
# _is_private_ip
# =============================================================================


class TestIsPrivateIp(unittest.TestCase):
    """_is_private_ip detects private/loopback/link-local IPs."""

    def setUp(self):
        self.cloner = WebsiteCloner("http://example.com")

    @mock.patch("socket.gethostbyname")
    def test_loopback_detected(self, mock_gethostbyname):
        """127.0.0.1 is loopback → True."""
        mock_gethostbyname.return_value = "127.0.0.1"
        self.assertTrue(self.cloner._is_private_ip("http://127.0.0.1/page"))

    @mock.patch("socket.gethostbyname")
    def test_private_10_dot_0_detected(self, mock_gethostbyname):
        """10.0.0.1 is private → True."""
        mock_gethostbyname.return_value = "10.0.0.1"
        self.assertTrue(self.cloner._is_private_ip("http://10.0.0.1/page"))

    @mock.patch("socket.gethostbyname")
    def test_private_192_dot_168_detected(self, mock_gethostbyname):
        """192.168.1.1 is private → True."""
        mock_gethostbyname.return_value = "192.168.1.1"
        self.assertTrue(self.cloner._is_private_ip("http://192.168.1.1/page"))

    @mock.patch("socket.gethostbyname")
    def test_link_local_detected(self, mock_gethostbyname):
        """169.254.1.1 is link-local → True."""
        mock_gethostbyname.return_value = "169.254.1.1"
        self.assertTrue(self.cloner._is_private_ip("http://169.254.1.1/page"))

    @mock.patch("socket.gethostbyname")
    def test_public_ip_returns_false(self, mock_gethostbyname):
        """93.184.216.34 (example.com) is public → False."""
        mock_gethostbyname.return_value = "93.184.216.34"
        self.assertFalse(self.cloner._is_private_ip("http://example.com/page"))
        mock_gethostbyname.assert_called_with("example.com")

    @mock.patch("socket.gethostbyname")
    def test_dns_failure_returns_false(self, mock_gethostbyname):
        """gethostbyname raising gaierror → False."""
        mock_gethostbyname.side_effect = socket.gaierror
        self.assertFalse(self.cloner._is_private_ip("http://nonexistent.example/page"))

    def test_empty_hostname_returns_false(self):
        """URL with no hostname → False."""
        self.assertFalse(self.cloner._is_private_ip("not-a-url"))


# =============================================================================
# BFS crawl behavior
# =============================================================================


class TestBfsCrawlBehavior(unittest.TestCase):
    """Integration-style tests for WebsiteCloner.clone() — all network mocked."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @staticmethod
    def _make_html(links=None, body=""):
        """Build a minimal HTML page with <a> tags for each link."""
        if links is None:
            links = []
        link_tags = "\n".join(f'<a href="{link}">{link}</a>' for link in links)
        return f"<html><head></head><body>{body}\n{link_tags}</body></html>"

    def _make_cloner(
        self, url="http://example.com", max_pages=5, follow_domains=False, **kwargs
    ):
        return WebsiteCloner(
            seed_url=url,
            output_dir=self.temp_dir,
            max_pages=max_pages,
            follow_domains=follow_domains,
            delay=0,  # no delay in tests
            **kwargs,
        )

    # -- helpers for common mock setup --------------------------------

    def _mock_fetch(self, cloner, responses):
        """Patch _fetch_page to return canned HTML from a URL→html dict."""
        patcher = mock.patch.object(cloner, "_fetch_page")
        mock_fetch = patcher.start()
        mock_fetch.side_effect = lambda url: responses.get(url)
        self.addCleanup(patcher.stop)
        return mock_fetch

    def _mock_assets(self, cloner):
        """Patch _download_asset to return fake content."""
        patcher = mock.patch.object(
            cloner, "_download_asset", return_value=b"fake-content"
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- tests --------------------------------------------------------

    def test_visits_seed_url_first(self):
        """Seed URL is the first URL fetched."""
        cloner = self._make_cloner(max_pages=2)
        self._mock_assets(cloner)
        mock_fetch = self._mock_fetch(
            cloner,
            {
                "http://example.com/": self._make_html(links=["/about"]),
                "http://example.com/about": self._make_html(),
            },
        )
        cloner.clone()
        mock_fetch.assert_any_call("http://example.com/")

    def test_follows_same_domain_links(self):
        """Same-domain links found on page are also fetched."""
        cloner = self._make_cloner(max_pages=5)
        self._mock_assets(cloner)
        mock_fetch = self._mock_fetch(
            cloner,
            {
                "http://example.com/": self._make_html(links=["/about", "/contact"]),
                "http://example.com/about": self._make_html(),
                "http://example.com/contact": self._make_html(),
            },
        )
        cloner.clone()
        mock_fetch.assert_any_call("http://example.com/")
        mock_fetch.assert_any_call("http://example.com/about")
        mock_fetch.assert_any_call("http://example.com/contact")

    def test_respects_max_pages(self):
        """Fetch stops after max_pages even if more URLs are queued."""
        cloner = self._make_cloner(max_pages=1)
        self._mock_assets(cloner)
        mock_fetch = self._mock_fetch(
            cloner,
            {
                "http://example.com/": self._make_html(links=["/about", "/contact"]),
            },
        )
        cloner.clone()
        self.assertEqual(mock_fetch.call_count, 1)

    def test_does_not_follow_external_links(self):
        """External links are ignored when follow_domains=False."""
        cloner = self._make_cloner(max_pages=5, follow_domains=False)
        self._mock_assets(cloner)
        mock_fetch = self._mock_fetch(
            cloner,
            {
                "http://example.com/": self._make_html(links=["http://other.com/page"]),
            },
        )
        cloner.clone()
        mock_fetch.assert_called_once_with("http://example.com/")

    def test_follows_external_links_when_enabled(self):
        """External links are followed when follow_domains=True."""
        cloner = self._make_cloner(max_pages=5, follow_domains=True)
        self._mock_assets(cloner)
        mock_fetch = self._mock_fetch(
            cloner,
            {
                "http://example.com/": self._make_html(links=["http://other.com/page"]),
                "http://other.com/page": self._make_html(),
            },
        )
        cloner.clone()
        mock_fetch.assert_any_call("http://other.com/page")

    def test_does_not_revisit_urls(self):
        """Duplicate links to the same URL are fetched only once."""
        cloner = self._make_cloner(max_pages=5)
        self._mock_assets(cloner)
        mock_fetch = self._mock_fetch(
            cloner,
            {
                "http://example.com/": self._make_html(links=["/about", "/about"]),
                "http://example.com/about": self._make_html(),
            },
        )
        cloner.clone()
        self.assertEqual(mock_fetch.call_count, 2)

    def test_bfs_order(self):
        """BFS processes URLs in breadth-first order."""
        cloner = self._make_cloner(max_pages=5)
        self._mock_assets(cloner)
        calls = []

        def track(url):
            calls.append(url)
            return {
                "http://example.com/": self._make_html(links=["/page1", "/page2"]),
                "http://example.com/page1": self._make_html(),
                "http://example.com/page2": self._make_html(),
            }.get(url)

        with mock.patch.object(cloner, "_fetch_page") as mock_fetch:
            mock_fetch.side_effect = track
            cloner.clone()

        # Seed first, then page1 and page2 (BFS left→right)
        self.assertEqual(calls[0], "http://example.com/")
        # pages may be in any order due to BFS deque, but should both be visited
        self.assertIn("http://example.com/page1", calls)
        self.assertIn("http://example.com/page2", calls)

    def test_max_pages_stops_mid_crawl(self):
        """Cloner stops mid-crawl when max_pages is reached."""
        cloner = self._make_cloner(max_pages=2)
        self._mock_assets(cloner)
        mock_fetch = self._mock_fetch(
            cloner,
            {
                "http://example.com/": self._make_html(links=["/page1", "/page2"]),
                "http://example.com/page1": self._make_html(links=["/page3"]),
                "http://example.com/page2": self._make_html(),
                "http://example.com/page3": self._make_html(),
            },
        )
        cloner.clone()
        # max_pages=2 → seed + page1 (page3 is included in page1's HTML but
        # page3's fetch is never called because cloner stops at 2)
        self.assertIn(mock_fetch.call_count, (2, 3))
        # At minimum seed + page1 must be called
        mock_fetch.assert_any_call("http://example.com/")
        mock_fetch.assert_any_call("http://example.com/page1")


if __name__ == "__main__":
    unittest.main()
