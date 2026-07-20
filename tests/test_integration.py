"""Integration test for WebsiteCloner — uses http.server to serve local fixtures."""

import http.server
import os
import shutil
import socket
import tempfile
import threading
import unittest
from unittest import mock

from cloner import WebsiteCloner

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _get_free_port() -> int:
    """Bind to an ephemeral port and return the port number."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class TestIntegrationLocalServer(unittest.TestCase):
    """End-to-end test serving fixtures via http.server."""

    def setUp(self):
        self.port = _get_free_port()
        self.output_dir = tempfile.mkdtemp()
        self.server_dir = FIXTURES_DIR

        # Start a simple HTTP server serving the fixtures directory
        handler = http.server.SimpleHTTPRequestHandler
        # Python 3.7+ accepts directory=; fall back to os.chdir if not available
        try:
            self.httpd = http.server.HTTPServer(
                ("127.0.0.1", self.port),
                lambda *a, **kw: handler(*a, directory=self.server_dir, **kw),
            )
        except TypeError:
            # Older Python — chdir to fixtures and chdir back in tearDown
            self._cwd = os.getcwd()
            os.chdir(self.server_dir)
            self.httpd = http.server.HTTPServer(("127.0.0.1", self.port), handler)

        self.server_thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True
        )
        self.server_thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.server_thread.join(timeout=2)
        shutil.rmtree(self.output_dir, ignore_errors=True)
        # Restore cwd if we changed it for older Python
        if hasattr(self, "_cwd"):
            os.chdir(self._cwd)

    def _seed_url(self):
        return f"http://127.0.0.1:{self.port}/index.html"

    def test_clones_seed_and_linked_page(self):
        """Clone fetches seed + linked page2, writing both to output dir."""
        cloner = WebsiteCloner(
            seed_url=self._seed_url(),
            output_dir=self.output_dir,
            max_pages=2,
            delay=0,
        )

        # Patch private-IP check to allow localhost
        with mock.patch.object(cloner, "_is_private_ip", return_value=False):
            cloner.clone()

        # Verify output directory exists and contains files
        self.assertTrue(os.path.isdir(self.output_dir))
        items = os.listdir(self.output_dir)

        # index.html should be present (seed page)
        self.assertIn(
            "index.html",
            items,
            f"Expected index.html in output, got: {items}",
        )

        # page2.html should be present (linked from index.html)
        self.assertIn(
            "page2.html",
            items,
            f"Expected page2.html in output, got: {items}",
        )

    def test_max_pages_limits_crawl(self):
        """Clone with max_pages=1 only fetches the seed page."""
        cloner = WebsiteCloner(
            seed_url=self._seed_url(),
            output_dir=self.output_dir,
            max_pages=1,
            delay=0,
        )

        with mock.patch.object(cloner, "_is_private_ip", return_value=False):
            cloner.clone()

        items = os.listdir(self.output_dir)
        self.assertIn("index.html", items)
        self.assertNotIn(
            "page2.html",
            items,
            f"page2.html should not exist with max_pages=1, got: {items}",
        )

    def test_output_dir_is_valid_directory(self):
        """The output directory exists and is a valid directory."""
        cloner = WebsiteCloner(
            seed_url=self._seed_url(),
            output_dir=self.output_dir,
            max_pages=2,
            delay=0,
        )

        with mock.patch.object(cloner, "_is_private_ip", return_value=False):
            result = cloner.clone()

        self.assertEqual(result, self.output_dir)
        self.assertTrue(os.path.isdir(self.output_dir))
        self.assertGreater(len(os.listdir(self.output_dir)), 0)
