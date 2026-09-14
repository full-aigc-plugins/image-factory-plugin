import multiprocessing
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import job_lock  # noqa: E402

HOLDER_TIMEOUT_SECONDS = 15.0


def _hold_lock(job_path: str, ready, release) -> None:
    """Acquire the job lock, announce it, and hold until told to stop."""
    with job_lock.JobLock(Path(job_path)):
        ready.put("locked")
        release.wait(timeout=HOLDER_TIMEOUT_SECONDS)


class JobLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.job_path = self.base / "job.json"

    def spawn_lock_holder(self, job_path: Path) -> multiprocessing.Process:
        """Hold the lock from a second process.

        A second lock object inside this process would prove nothing about
        cross-process exclusion, so the holder is a real child process.
        """
        context = multiprocessing.get_context("spawn")
        self.ready = context.Queue()
        self.release = context.Event()
        process = context.Process(
            target=_hold_lock,
            args=(str(job_path), self.ready, self.release),
            daemon=True,
        )
        process.start()
        self.addCleanup(self._stop_holder, process)
        return process

    def _stop_holder(self, process: multiprocessing.Process) -> None:
        self.release.set()
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)

    def test_lock_path_derives_from_the_job_file(self) -> None:
        self.assertEqual(job_lock.lock_path_for(Path("/tmp/job.json")), Path("/tmp/job.json.lock"))

    def test_a_free_job_can_be_locked_and_released(self) -> None:
        with job_lock.JobLock(self.job_path):
            self.assertTrue(job_lock.lock_path_for(self.job_path).is_file())
        with job_lock.JobLock(self.job_path):
            pass

    def test_the_lock_file_is_created_next_to_the_job(self) -> None:
        with job_lock.JobLock(self.job_path):
            self.assertEqual(
                job_lock.lock_path_for(self.job_path).parent, self.job_path.parent
            )

    def test_second_process_cannot_acquire_the_same_job(self) -> None:
        process = self.spawn_lock_holder(self.job_path)
        self.assertEqual(self.ready.get(timeout=5), "locked")
        with self.assertRaises(job_lock.JobAlreadyRunningError):
            with job_lock.JobLock(self.job_path):
                self.fail("second process acquired an active job")
        self.release.set()
        process.join(timeout=5)
        with job_lock.JobLock(self.job_path):
            pass
        self.assertFalse(process.is_alive())

    def test_contention_fails_immediately_by_default(self) -> None:
        """A contended job must refuse rather than hang the caller."""
        process = self.spawn_lock_holder(self.job_path)
        self.assertEqual(self.ready.get(timeout=5), "locked")
        with self.assertRaises(job_lock.JobAlreadyRunningError):
            job_lock.JobLock(self.job_path).__enter__()
        self.release.set()
        process.join(timeout=5)

    def test_the_lock_is_released_when_the_body_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            with job_lock.JobLock(self.job_path):
                raise RuntimeError("boom")
        with job_lock.JobLock(self.job_path):
            pass

    def test_missing_parent_directories_are_created(self) -> None:
        nested = self.base / "state" / "job.json"
        with job_lock.JobLock(nested):
            self.assertTrue(job_lock.lock_path_for(nested).is_file())

    def test_unrelated_io_errors_are_not_reported_as_contention(self) -> None:
        """An unusable path must surface the real error, never a fake conflict."""
        blocker = self.base / "blocker"
        blocker.write_text("this is a file, not a directory", encoding="utf-8")
        with self.assertRaises(OSError) as caught:
            with job_lock.JobLock(blocker / "job.json"):
                self.fail("a lock beneath a plain file should not succeed")
        self.assertNotIsInstance(caught.exception, job_lock.JobAlreadyRunningError)


if __name__ == "__main__":
    unittest.main()
