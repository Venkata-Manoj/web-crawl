"""
Unit tests for JobStore — thread-safe in-memory job tracking.

Tests cover create+get, list (with copy isolation), update, delete,
and TTL-based pruning.
"""

import time
import unittest

from web_crawl.webjobs import JobStore


class TestJobStore(unittest.TestCase):
    """JobStore CRUD and TTL pruning."""

    def setUp(self):
        self.store = JobStore(ttl=3600)

    # -- create + get -------------------------------------------------------

    def test_create_and_get(self):
        """A created job is retrievable by its ID."""
        job_id = self.store.create("http://example.com")
        job = self.store.get(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job["url"], "http://example.com")
        self.assertEqual(job["status"], "running")
        self.assertEqual(job["pages_cloned"], 0)

    def test_get_returns_copy(self):
        """Modifying the returned dict does not affect the stored job."""
        job_id = self.store.create("http://example.com")
        job1 = self.store.get(job_id)
        job1["status"] = "done"
        job2 = self.store.get(job_id)
        self.assertEqual(job2["status"], "running")

    def test_get_nonexistent_returns_none(self):
        """Fetching a missing job returns None."""
        self.assertIsNone(self.store.get("nonexistent"))

    # -- list ---------------------------------------------------------------

    def test_list_returns_all_jobs(self):
        """list() contains every created job."""
        id1 = self.store.create("http://example.com")
        id2 = self.store.create("http://other.com")
        jobs = self.store.list()
        self.assertIn(id1, jobs)
        self.assertIn(id2, jobs)
        self.assertEqual(len(jobs), 2)

    def test_list_returns_copies(self):
        """Modifying the returned dict does not affect the store."""
        self.store.create("http://example.com")
        jobs = self.store.list()
        for jid in list(jobs.keys()):
            jobs.pop(jid)
        self.assertEqual(len(self.store.list()), 1)

    # -- update -------------------------------------------------------------

    def test_update_modifies_job(self):
        """update() changes the specified fields and returns True."""
        job_id = self.store.create("http://example.com", max_pages=50)
        result = self.store.update(job_id, status="done", pages_cloned=10)
        self.assertTrue(result)
        job = self.store.get(job_id)
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["pages_cloned"], 10)
        self.assertEqual(job["max_pages"], 50)

    def test_update_nonexistent_returns_false(self):
        """update() returns False for a missing job."""
        result = self.store.update("nonexistent", status="done")
        self.assertFalse(result)

    # -- delete -------------------------------------------------------------

    def test_delete_removes_job(self):
        """delete() permanently removes the job."""
        job_id = self.store.create("http://example.com")
        self.assertIsNotNone(self.store.get(job_id))
        self.store.delete(job_id)
        self.assertIsNone(self.store.get(job_id))

    def test_delete_nonexistent_does_not_raise(self):
        """delete() on a missing job is a no-op."""
        self.store.delete("nonexistent")  # should not raise

    # -- prune --------------------------------------------------------------

    def test_prune_expired_removes_old_jobs(self):
        """Jobs older than TTL are removed by prune_expired()."""
        store = JobStore(ttl=0.1)
        store.create("http://example.com")
        self.assertEqual(len(store.list()), 1)
        time.sleep(0.15)
        pruned = store.prune_expired()
        self.assertEqual(pruned, 1)
        self.assertEqual(len(store.list()), 0)

    def test_prune_expired_noop_for_fresh_jobs(self):
        """Jobs within TTL are preserved."""
        self.store.create("http://example.com")
        pruned = self.store.prune_expired()
        self.assertEqual(pruned, 0)
        self.assertEqual(len(self.store.list()), 1)

    def test_prune_expired_keeps_fresh_jobs(self):
        """Only expired jobs are removed; fresh ones survive."""
        store = JobStore(ttl=0.1)
        store.create("http://old.com")
        time.sleep(0.15)
        fresh_id = store.create("http://fresh.com")
        pruned = store.prune_expired()
        self.assertEqual(pruned, 1)
        jobs = store.list()
        self.assertEqual(len(jobs), 1)
        self.assertIn(fresh_id, jobs)
