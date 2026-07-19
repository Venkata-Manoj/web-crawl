"""Security checks for Website Cloner — SSRF, path traversal, scheme validation, path length limits."""

import hashlib
import ipaddress
import os
import socket
from urllib.parse import urlparse


def is_private_ip(url: str) -> bool:
    """Check if a URL resolves to a private or loopback IP address.

    This is an SSRF-prevention check extracted from the original
    WebsiteCloner._is_private_ip.
    """
    hostname = urlparse(url).hostname
    if not hostname:
        return False
    try:
        ip = socket.gethostbyname(hostname)
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except (socket.gaierror, ValueError):
        return False


def safe_path(local_path: str, output_dir: str) -> str:
    """Sanitize *local_path* to prevent path traversal and filename length issues.

    1. Resolves ``..`` sequences and ensures the resulting path stays within
       *output_dir* (path traversal protection).
    2. If any path component exceeds 200 characters, the **last component**
       (filename) is replaced with an MD5 hash to avoid ``ENAMETOOLONG``
       errors on filesystems with a 255-byte component limit.
    3. If traversal is detected the path is hashed to a safe name (preserving
       any extension).
    """
    full_path = os.path.abspath(os.path.join(output_dir, local_path))
    output_dir_abs = os.path.abspath(output_dir)

    # ── Path-traversal guard ────────────────────────────────────────────
    if os.path.commonpath([full_path, output_dir_abs]) != output_dir_abs:
        ext = os.path.splitext(local_path)[1]
        return hashlib.md5(local_path.encode()).hexdigest()[:16] + ext

    rel = os.path.relpath(full_path, output_dir)

    # ── Filename-length guard ───────────────────────────────────────────
    parts = rel.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if len(part) > 200:
            # Hash the full original URL path to keep it deterministic
            ext = os.path.splitext(part)[1]
            parts[i] = hashlib.md5(part.encode()).hexdigest()[:16] + ext

    rel = os.path.join(*parts)
    return rel


def validate_scheme(url: str) -> bool:
    """Check that *url* uses an http or https scheme only.

    Returns ``True`` for http/https, ``False`` for file:, javascript:,
    data:, vbscript:, etc.
    """
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https")
