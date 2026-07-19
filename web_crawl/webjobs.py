"""
Thread-safe in-memory job store with TTL-based pruning.

Provides create/get/list/update/delete operations protected by a
threading.Lock. Jobs older than *ttl* seconds are removed by
prune_expired(), which is safe to call on a periodic timer.
"""

import threading
import time
from datetime import datetime


class JobStore:
    """Thread-safe in-memory store for crawl jobs with TTL-based pruning."""

    def __init__(self, ttl: int = 3600):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._jobs: dict = {}

    def create(self, url: str, max_pages: int = 100) -> str:
        """Create a new job and return its ID."""
        job_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
        job = {
            "id": job_id,
            "url": url,
            "status": "running",
            "pages_cloned": 0,
            "max_pages": max_pages,
            "current_url": "",
            "output_dir": "",
            "error": None,
            "started_at": datetime.now().isoformat(),
        }
        with self._lock:
            self._jobs[job_id] = {
                "data": job,
                "created_at": time.time(),
            }
        return job_id

    def get(self, job_id: str) -> dict | None:
        """Return a shallow copy of the job, or *None* if not found."""
        with self._lock:
            entry = self._jobs.get(job_id)
            if entry is None:
                return None
            return dict(entry["data"])

    def list(self) -> dict:
        """Return a dict of all jobs keyed by job ID (shallow copies)."""
        with self._lock:
            return {jid: dict(entry["data"]) for jid, entry in self._jobs.items()}

    def update(self, job_id: str, **updates) -> bool:
        """Update arbitrary fields on a job.

        Returns *True* if the job existed, *False* otherwise.
        """
        with self._lock:
            entry = self._jobs.get(job_id)
            if entry is None:
                return False
            entry["data"].update(updates)
            return True

    def delete(self, job_id: str) -> None:
        """Remove a job from the store.  No-op if the job does not exist."""
        with self._lock:
            self._jobs.pop(job_id, None)

    def prune_expired(self) -> int:
        """Remove jobs whose age exceeds *ttl*.  Returns the number pruned."""
        cutoff = time.time() - self._ttl
        with self._lock:
            expired = [
                jid for jid, entry in self._jobs.items() if entry["created_at"] < cutoff
            ]
            for jid in expired:
                del self._jobs[jid]
            return len(expired)
