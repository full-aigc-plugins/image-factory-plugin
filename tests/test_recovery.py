import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import image_factory_cli as cli  # noqa: E402
import receipt_store  # noqa: E402
from tests.test_cli import SHIM, CliFixture  # noqa: E402


class RecoveryCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CliFixture()
        self.addCleanup(self.fixture.cleanup)
        self.fixture.write_plan()
        self.fixture.control()
        result = self.fixture.run_approved_batch()
        self.receipts = result["receipts"]

    def recover(self) -> tuple[int, dict]:
        invocation_evidence_before = tuple(self.fixture.base.rglob("*last-message.txt"))
        with patch.object(
            cli.generation_runner,
            "run_item",
            side_effect=AssertionError("recovery must make zero Codex calls"),
        ):
            code, output = self.fixture.run_cli(
                "recover",
                "--plan",
                str(self.fixture.plan_path),
                "--job",
                str(self.fixture.job_path),
                "--destination",
                str(self.fixture.destination),
                "--json",
            )
        self.assertEqual(
            tuple(self.fixture.base.rglob("*last-message.txt")),
            invocation_evidence_before,
            "recovery must create no invocation evidence",
        )
        return code, json.loads(output)

    def rewrite_item(self, index: int, state: str) -> None:
        ledger = self.fixture.read_job()
        ledger["state"] = "Unknown" if state == "Unknown" else "Running"
        row = ledger["items"][index]
        row["state"] = state
        row["receipt_id"] = None
        row["error_category"] = "unknown" if state == "Unknown" else None
        self.fixture.job_path.write_text(json.dumps(ledger), encoding="utf-8")

    def test_attempting_with_verified_receipt_becomes_generated(self) -> None:
        self.rewrite_item(0, "Attempting")
        code, report = self.recover()
        self.assertEqual(code, cli.EXIT_OK, report)
        self.assertEqual(report["state"], "Completed")
        self.assertEqual(report["reconciled"], ["item-01"])
        self.assertEqual(self.fixture.read_job()["items"][0]["state"], "Generated")

    def test_attempting_without_receipt_becomes_unknown(self) -> None:
        self.rewrite_item(0, "Attempting")
        receipt_store.receipt_path(
            self.fixture.job_path, self.receipts[0]["idempotency_key"]
        ).unlink()
        receipt_store.manifest_path(self.fixture.job_path).unlink()
        code, report = self.recover()
        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED, report)
        self.assertEqual(report["state"], "Unknown")
        self.assertEqual(report["unknown"], ["item-01"])
        self.assertEqual(report["remaining_generation_calls"], 0)
        self.assertEqual(self.fixture.read_job()["items"][0]["state"], "Unknown")

    def test_aggregate_manifest_alone_cannot_reconcile_an_attempt(self) -> None:
        self.rewrite_item(0, "Attempting")
        receipt_store.receipt_path(
            self.fixture.job_path, self.receipts[0]["idempotency_key"]
        ).unlink()
        code, report = self.recover()
        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED, report)
        self.assertEqual(report["unknown"], ["item-01"])

    def test_unknown_with_verified_receipt_becomes_generated(self) -> None:
        self.rewrite_item(0, "Unknown")
        code, report = self.recover()
        self.assertEqual(code, cli.EXIT_OK, report)
        self.assertEqual(report["state"], "Completed")
        self.assertEqual(report["reconciled"], ["item-01"])

    def test_recovery_rebuilds_manifest_from_verified_receipts(self) -> None:
        self.rewrite_item(0, "Attempting")
        receipt_store.manifest_path(self.fixture.job_path).unlink()
        code, _report = self.recover()
        self.assertEqual(code, cli.EXIT_OK)
        rebuilt = json.loads(
            receipt_store.manifest_path(self.fixture.job_path).read_text(encoding="utf-8")
        )
        self.assertEqual({row["item_id"] for row in rebuilt}, {"item-01", "item-02"})

    def test_tampered_receipt_is_refused_without_mutating_the_ledger(self) -> None:
        self.rewrite_item(0, "Attempting")
        before = self.fixture.job_path.read_bytes()
        artifact = self.fixture.destination / self.receipts[0]["path"]
        artifact.write_bytes(b"tampered")
        code, report = self.recover()
        self.assertEqual(code, cli.EXIT_FAILURE, report)
        self.assertIn("artifact verification", report["error"])
        self.assertEqual(self.fixture.job_path.read_bytes(), before)

    def test_unresolved_unknown_blocks_an_ordinary_run(self) -> None:
        self.rewrite_item(0, "Attempting")
        receipt_store.receipt_path(
            self.fixture.job_path, self.receipts[0]["idempotency_key"]
        ).unlink()
        receipt_store.manifest_path(self.fixture.job_path).unlink()
        code, _report = self.recover()
        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED)

        with patch.object(
            cli.generation_runner,
            "run_item",
            side_effect=AssertionError("unknown work must not be retried"),
        ):
            code, output = self.fixture.run_cli(
                "run",
                "--plan",
                str(self.fixture.plan_path),
                "--job",
                str(self.fixture.job_path),
                "--codex-bin",
                str(SHIM),
                *self.fixture.base_args(),
                "--approve",
                "--json",
            )
        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED, output)


if __name__ == "__main__":
    unittest.main()
