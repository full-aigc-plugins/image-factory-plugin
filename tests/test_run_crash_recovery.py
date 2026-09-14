import json
import unittest
from unittest.mock import patch

from tests.test_cli import CliFixture, SHIM

import image_factory_cli as cli


class RunCrashRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CliFixture()
        self.addCleanup(self.fixture.cleanup)
        self.fixture.write_plan()
        self.invocation_dir = self.fixture.base / "invocations"
        self.fixture.control(invocation_dir=str(self.invocation_dir))

    def run_batch(self) -> tuple[int, str]:
        return self.fixture.run_cli(
            "run", "--plan", str(self.fixture.plan_path), "--job", str(self.fixture.job_path),
            "--codex-bin", str(SHIM), *self.fixture.base_args(), "--approve", "--json",
        )

    def ledger(self) -> dict:
        return json.loads(self.fixture.job_path.read_text(encoding="utf-8"))

    def test_crash_before_attempt_leaves_item_unreserved(self) -> None:
        with patch.object(cli.job_ledger.JobLedger, "start_attempt", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_batch()
        self.assertEqual(self.ledger()["items"], [])

    def test_crash_after_invocation_leaves_attempt_ambiguous(self) -> None:
        original = cli.generation_runner.run_item
        def invoked(**kwargs):
            original(**kwargs)
            raise KeyboardInterrupt
        with patch.object(cli.generation_runner, "run_item", side_effect=invoked):
            with self.assertRaises(KeyboardInterrupt):
                self.run_batch()
        self.assertEqual(len(list(self.invocation_dir.glob("*.json"))), 1)
        self.assertEqual(self.ledger()["items"][0]["state"], "Attempting")

    def test_crash_after_publication_before_receipt_leaves_attempt_ambiguous(self) -> None:
        with patch.object(cli.receipt_store, "write_receipt", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_batch()
        self.assertEqual(self.ledger()["items"][0]["state"], "Attempting")
        self.assertTrue(list(self.fixture.destination.rglob("*.png")))

    def test_crash_after_receipt_before_completion_is_reconcilable(self) -> None:
        with patch.object(cli.job_ledger.JobLedger, "complete_attempt", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_batch()
        self.assertEqual(self.ledger()["items"][0]["state"], "Attempting")
        self.assertEqual(len(list((self.fixture.base / "job.json.receipts").glob("*.json"))), 1)

    def test_crash_after_completion_before_manifest_keeps_generated_item(self) -> None:
        with patch.object(cli.receipt_store, "rebuild_manifest", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_batch()
        self.assertTrue(all(row["state"] == "Generated" for row in self.ledger()["items"]))


if __name__ == "__main__":
    unittest.main()
