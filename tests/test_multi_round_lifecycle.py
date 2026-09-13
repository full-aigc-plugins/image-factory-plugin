import json
import unittest
from unittest.mock import patch

from tests.test_cli import CliFixture, SHIM

import image_factory_cli as cli
import receipt_store


class MultiRoundLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CliFixture()
        self.addCleanup(self.fixture.cleanup)
        self.fixture.write_plan()
        self.fixture.control()
        self.fixture.run_approved_batch()
        self.scores = self.fixture.base / "scores.json"
        labels = self.fixture.base / "labels.json"
        labels.write_text(
            json.dumps({"item-01": "rejected", "item-02": "approved"}), encoding="utf-8"
        )
        code, output = self.fixture.run_cli(
            "evaluate", "--plan", str(self.fixture.plan_path), "--job", str(self.fixture.job_path),
            "--scores", str(self.scores), "--labels", str(labels), *self.fixture.base_args(), "--json",
        )
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        rewrites = self.fixture.base / "rewrites.json"
        rewrites.write_text(json.dumps({"item-01": "a calmer round two portrait"}), encoding="utf-8")
        self.round_two_plan = self.fixture.base / "round-two.json"
        code, output = self.fixture.run_cli(
            "optimize", "--job", str(self.fixture.job_path), "--plan", str(self.fixture.plan_path),
            "--scores", str(self.scores), "--rewrites", str(rewrites),
            "--out", str(self.round_two_plan), "--json",
        )
        self.assertEqual(code, cli.EXIT_OK, output)

    def run_round_two(self) -> tuple[int, str]:
        return self.fixture.run_cli(
            "run", "--plan", str(self.round_two_plan), "--job", str(self.fixture.job_path),
            "--codex-bin", str(SHIM), *self.fixture.base_args(), "--approve", "--json",
        )

    def test_round_two_generation_evaluation_and_status_ignore_round_one_history(self) -> None:
        code, output = self.run_round_two()
        self.assertEqual(code, cli.EXIT_OK, output)
        self.assertEqual(len(self.fixture.read_job()["items"]), 3)
        code, output = self.fixture.run_cli("status", "--job", str(self.fixture.job_path), "--json")
        self.assertEqual(code, cli.EXIT_OK, output)
        status = json.loads(output)
        self.assertEqual(status["counts"]["generated"], 1)
        self.assertEqual(sum(status["counts"].values()), 1)
        round_two_scores = self.fixture.base / "round-two-scores.json"
        code, output = self.fixture.run_cli(
            "evaluate", "--plan", str(self.round_two_plan), "--job", str(self.fixture.job_path),
            "--scores", str(round_two_scores), *self.fixture.base_args(), "--json",
        )
        self.assertEqual(code, cli.EXIT_OK, output)
        self.assertEqual(json.loads(round_two_scores.read_text(encoding="utf-8"))["round"], 2)

    def test_stale_round_one_receipt_cannot_mask_a_missing_round_two_receipt(self) -> None:
        code, output = self.run_round_two()
        self.assertEqual(code, cli.EXIT_OK, output)
        current = cli.plan_validator.validate_plan(
            json.loads(self.round_two_plan.read_text(encoding="utf-8")),
            base_dir=self.round_two_plan.parent,
        ).items[0]
        receipt_store.receipt_path(self.fixture.job_path, current.idempotency_key).unlink()
        receipt_store.manifest_path(self.fixture.job_path).unlink()
        before = self.scores.read_bytes()
        code, output = self.fixture.run_cli(
            "evaluate", "--plan", str(self.round_two_plan), "--job", str(self.fixture.job_path),
            "--scores", str(self.scores), *self.fixture.base_args(), "--json",
        )
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertEqual(self.scores.read_bytes(), before)

    def test_round_two_receipt_must_match_the_current_ledger_receipt_id(self) -> None:
        code, output = self.run_round_two()
        self.assertEqual(code, cli.EXIT_OK, output)
        ledger = self.fixture.read_job()
        ledger["items"][-1]["receipt_id"] = "stale-ledger-receipt"
        cli.job_ledger.write_ledger(self.fixture.job_path, ledger)
        code, output = self.fixture.run_cli(
            "evaluate", "--plan", str(self.round_two_plan), "--job", str(self.fixture.job_path),
            "--scores", str(self.fixture.base / "round-two-scores.json"),
            *self.fixture.base_args(), "--json",
        )
        self.assertEqual(code, cli.EXIT_FAILURE, output)

    def test_round_two_crash_after_receipt_recovers_without_rejecting_history(self) -> None:
        with patch.object(cli.job_ledger.JobLedger, "complete_attempt", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_round_two()
        with patch.object(cli.generation_runner, "run_item", side_effect=AssertionError("no retry")):
            code, output = self.fixture.run_cli(
                "recover", "--plan", str(self.round_two_plan), "--job", str(self.fixture.job_path),
                "--destination", str(self.fixture.destination), "--json",
            )
        self.assertEqual(code, cli.EXIT_OK, output)
        report = json.loads(output)
        self.assertEqual(report["completed_count"], 1)
        self.assertEqual(report["pending_count"], 0)
        self.assertEqual(report["unknown_count"], 0)

    def test_round_two_crash_before_attempt_leaves_current_item_pending(self) -> None:
        with patch.object(cli.job_ledger.JobLedger, "start_attempt", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_round_two()
        code, output = self.fixture.run_cli("status", "--job", str(self.fixture.job_path), "--json")
        self.assertEqual(code, cli.EXIT_OK, output)
        self.assertEqual(json.loads(output)["counts"]["pending"], 1)

    def test_round_two_crash_after_invocation_recovers_as_unknown_without_retry(self) -> None:
        original = cli.generation_runner.run_item

        def invoked(**kwargs):
            original(**kwargs)
            raise KeyboardInterrupt

        with patch.object(cli.generation_runner, "run_item", side_effect=invoked):
            with self.assertRaises(KeyboardInterrupt):
                self.run_round_two()
        code, output = self.fixture.run_cli(
            "recover", "--plan", str(self.round_two_plan), "--job", str(self.fixture.job_path),
            "--destination", str(self.fixture.destination), "--json",
        )
        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED, output)
        self.assertEqual(json.loads(output)["unknown_count"], 1)

    def test_round_two_crash_after_publication_before_receipt_recovers_as_unknown(self) -> None:
        with patch.object(cli.receipt_store, "write_receipt", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_round_two()
        code, output = self.fixture.run_cli(
            "recover", "--plan", str(self.round_two_plan), "--job", str(self.fixture.job_path),
            "--destination", str(self.fixture.destination), "--json",
        )
        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED, output)
        self.assertEqual(json.loads(output)["unknown_count"], 1)

    def test_round_two_crash_after_completion_rebuilds_manifest_from_current_receipt(self) -> None:
        with patch.object(cli.receipt_store, "rebuild_manifest", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_round_two()
        code, output = self.fixture.run_cli(
            "recover", "--plan", str(self.round_two_plan), "--job", str(self.fixture.job_path),
            "--destination", str(self.fixture.destination), "--json",
        )
        self.assertEqual(code, cli.EXIT_OK, output)
        manifest = json.loads(receipt_store.manifest_path(self.fixture.job_path).read_text(encoding="utf-8"))
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0]["round"], 2)


if __name__ == "__main__":
    unittest.main()
