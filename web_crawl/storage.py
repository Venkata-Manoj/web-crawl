"""File storage for Website Cloner v2 — write, stream, and track sizes."""

import logging
import os

from .config import MAX_TOTAL_BYTES

logger = logging.getLogger(__name__)


class Storage:
    """Write files to disk and keep track of total bytes / file count.

    Usage::

        store = Storage()
        store.safe_write(html_bytes, "index.html", "/tmp/output")
        print(store.total_bytes, store.file_count)
    """

    def __init__(self, max_total_bytes: int = MAX_TOTAL_BYTES):
        self.total_bytes: int = 0
        self.file_count: int = 0
        self.max_total_bytes = max_total_bytes

    def _check_limit(self, additional: int) -> bool:
        if self.total_bytes + additional > self.max_total_bytes:
            logger.warning(
                f"Total download would exceed {self.max_total_bytes} byte limit"
            )
            return False
        return True

    def safe_write(self, content: bytes, local_path: str, output_dir: str) -> str:
        """Write *content* (bytes) to ``output_dir/local_path``.

        Creates parent directories as needed.  Returns the absolute path of
        the written file, or ``None`` if the size limit would be exceeded.
        """
        if not self._check_limit(len(content)):
            return None
        full_path = os.path.join(output_dir, local_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(content)
        self.total_bytes += len(content)
        self.file_count += 1
        return full_path

    def safe_write_text(self, text: str, local_path: str, output_dir: str) -> str:
        """Write *text* (str, UTF-8 encoded) to ``output_dir/local_path``."""
        encoded = text.encode("utf-8")
        return self.safe_write(encoded, local_path, output_dir)

    def stream_write(self, iterable, local_path: str, output_dir: str) -> str:
        """Stream-write chunks from *iterable* to ``output_dir/local_path``.

        Each chunk is written immediately so large payloads don't need to
        be held in memory.
        """
        full_path = os.path.join(output_dir, local_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            for chunk in iterable:
                if not self._check_limit(len(chunk)):
                    return None
                f.write(chunk)
                self.total_bytes += len(chunk)
        self.file_count += 1
        return full_path
