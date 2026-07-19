"""Per-domain token bucket rate limiter for Website Cloner v2."""

import time
import threading


class DomainRateLimiter:
    """Per-domain token bucket rate limiter.

    Thread-safe.  Each domain gets its own bucket created on first
    ``acquire()`` call.  If no tokens are available the caller blocks
    until enough tokens have been refilled.
    """

    def __init__(self, default_rate: float = 10.0, default_burst: int = 20):
        self.default_rate = default_rate
        self.default_burst = default_burst
        self._buckets: dict[str, dict] = {}
        self._lock = threading.Lock()

    def acquire(self, domain: str, tokens: int = 1) -> None:
        """Block until *tokens* are available for *domain*."""
        while True:
            with self._lock:
                bucket = self._buckets.get(domain)
                if bucket is None:
                    bucket = {
                        "tokens": self.default_burst,
                        "rate": self.default_rate,
                        "max_burst": self.default_burst,
                        "last_refill": time.monotonic(),
                    }
                    self._buckets[domain] = bucket
                now = time.monotonic()
                elapsed = now - bucket["last_refill"]
                bucket["tokens"] = min(
                    bucket["max_burst"],
                    bucket["tokens"] + elapsed * bucket["rate"],
                )
                bucket["last_refill"] = now
                if bucket["tokens"] >= tokens:
                    bucket["tokens"] -= tokens
                    return
                deficit = tokens - bucket["tokens"]
                sleep_time = deficit / bucket["rate"]
            time.sleep(sleep_time)
