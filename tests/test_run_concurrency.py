import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.test_cli import CliFixture, SHIM

import image_factory_cli as cli


class RunConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CliFixture()
        self.addCleanup(self.fixture.cleanup)
        self.fixture.write_plan()
        self.invocation_dir = self.fixture.base / "invocations"
        self.fixture.control(invocation_dir=str(self.invocation_dir), delay_before_result_seconds=0.5)

    def receipts_for_unique_idempotency_keys(self) -> set[str]:
        directory = self.fixture.base / "job.json.receipts"
        return {json.loads(path.read_text(encoding="utf-8"))["idempotency_key"] for path in directory.glob("*.json")}

    def test_only_one_process_can_spend_the_batch(self) -> None:
        command = [
            sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "image_factory_cli.py"), "run",
            "--plan", str(self.fixture.plan_path), "--job", str(self.fixture.job_path),
            "--codex-bin", str(SHIM), *self.fixture.base_args(), "--approve", "--json",
        ]
        environment = os.environ.copy()
        environment["FAKE_CODEX_CONTROL"] = str(self.fixture.control_path)
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=environment) for _ in range(2)]
        results = [process.communicate(timeout=20) + (process.returncode,) for process in processes]
        self.assertEqual(sorted(result[2] for result in results), [0, cli.EXIT_JOB_LOCKED])
        self.assertEqual(len(list(self.invocation_dir.glob("*.json"))), 2)
        self.assertEqual(len(self.receipts_for_unique_idempotency_keys()), 2)


if __name__ == "__main__":
    unittest.main()
