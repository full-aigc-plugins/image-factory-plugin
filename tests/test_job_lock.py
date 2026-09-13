import multiprocessing
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import job_lock  # noqa: E402


def hold_lock(job_path: Path, ready, release) -> None:
    with job_lock.JobLock(job_path):
        ready.put("locked")
        release.wait(timeout=5)


class JobLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.job_path = Path(self._tmp.name) / "job.json"
        context = multiprocessing.get_context("spawn")
        self.ready = context.Queue()
        self.release = context.Event()
        self.addCleanup(self.release.set)

    def spawn_lock_holder(self, job_path: Path) -> multiprocessing.Process:
        context = multiprocessing.get_context("spawn")
        process = context.Process(
            target=hold_lock,
            args=(job_path, self.ready, self.release),
        )
        process.start()
        self.addCleanup(lambda: process.join(timeout=5))
        return process

    def test_second_process_cannot_acquire_the_same_job(self) -> None:
        process = self.spawn_lock_holder(self.job_path)
        self.assertEqual(self.ready.get(timeout=5), "locked")
        with self.assertRaises(job_lock.JobAlreadyRunningError):
            with job_lock.JobLock(self.job_path):
                self.fail("second process acquired active job")
        self.release.set()
        process.join(timeout=5)
        self.assertFalse(process.is_alive(), "lock holder did not exit")
        with job_lock.JobLock(self.job_path):
            pass


if __name__ == "__main__":
    unittest.main()
