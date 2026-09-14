import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import image_factory_cli as cli  # noqa: E402
import job_lock  # noqa: E402


FAKE = ROOT / "tests" / "fakes" / "fake_codex.py"
REAL_PNG = ROOT / "assets" / "logo.png"


def fast_python() -> str:
    candidate = Path(sys.base_prefix) / "bin" / "python3"
    return str(candidate) if candidate.is_file() else sys.executable


def build_shim() -> Path:
    directory = Path(tempfile.mkdtemp(prefix="image-factory-cli-shim-"))
    shim = directory / "codex"
    shim.write_text(f'#!/bin/sh\nexec "{fast_python()}" "{FAKE}" "$@"\n', encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return shim


SHIM = build_shim()


def valid_plan(**overrides) -> dict:
    document = {
        "schema_version": "1.0.0",
        "batch_id": "portrait-study",
        "round": 1,
        "goal": "match the reference lighting",
        "limits": {"max_images": 20, "max_rounds": 3, "require_approval_before_run": True},
        "judge_policy": {"min_dimension": 64, "reject_duplicates": True, "pass_threshold": 0.8},
        "items": [
            {"id": "item-01", "prompt": "a calm portrait"},
            {"id": "item-02", "prompt": "a second portrait"},
        ],
    }
    document.update(overrides)
    return document


class CliFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.codex_home = self.base / "codex-home"
        self.codex_home.mkdir()
        (self.codex_home / "auth.json").write_text("{}", encoding="utf-8")
        (self.codex_home / "config.toml").write_text('model = "gpt-5.6-sol"\n', encoding="utf-8")
        self.generation_dir = self.codex_home / "generated_images"
        self.generation_dir.mkdir()
        self.plan_path = self.base / "plan.json"
        self.job_path = self.base / "job.json"
        self.destination = self.base / "batch-out"
        self.control_path = self.base / "control.json"
        self._previous_env: str | None = None

    def write_plan(self, document: dict | None = None) -> Path:
        self.plan_path.write_text(json.dumps(document or valid_plan()), encoding="utf-8")
        return self.plan_path

    def control(self, **values) -> None:
        values.setdefault("mode", "generate")
        values.setdefault("generation_dir", str(self.generation_dir))
        values.setdefault("png_source", str(REAL_PNG))
        self.control_path.write_text(json.dumps(values), encoding="utf-8")
        self._previous_env = os.environ.get("FAKE_CODEX_CONTROL")
        os.environ["FAKE_CODEX_CONTROL"] = str(self.control_path)

    def run_cli(self, *args: str) -> tuple[int, str]:
        return cli.run_cli(list(args))

    def read_job(self) -> dict:
        return json.loads(self.job_path.read_text(encoding="utf-8"))

    def run_approved_batch(self) -> tuple[int, str]:
        return self.run_cli(
            "run",
            "--plan",
            str(self.plan_path),
            "--job",
            str(self.job_path),
            "--codex-bin",
            str(SHIM),
            *self.base_args(),
            "--approve",
            "--json",
        )

    def evaluate_batch(self, *extra: str) -> tuple[int, str]:
        return self.run_cli(
            "evaluate",
            "--plan",
            str(self.plan_path),
            "--job",
            str(self.job_path),
            "--scores",
            str(self.base / "scores.json"),
            *self.base_args(),
            "--json",
            *extra,
        )

    def base_args(self) -> list[str]:
        return [
            "--codex-home",
            str(self.codex_home),
            "--generation-dir",
            str(self.generation_dir),
            "--destination",
            str(self.destination),
        ]

    def cleanup(self) -> None:
        if self._previous_env is None:
            os.environ.pop("FAKE_CODEX_CONTROL", None)
        else:
            os.environ["FAKE_CODEX_CONTROL"] = self._previous_env
        self._tmp.cleanup()


class ProbeCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CliFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_probe_succeeds_on_a_ready_environment(self) -> None:
        code, output = self.fixture.run_cli(
            "probe",
            "--codex-home",
            str(self.fixture.codex_home),
            "--codex-bin",
            str(SHIM),
            "--json",
        )
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["verdict"], "available")

    def test_probe_fails_with_a_distinct_code_when_unavailable(self) -> None:
        bare = self.fixture.base / "bare-home"
        bare.mkdir()
        code, output = self.fixture.run_cli("probe", "--codex-home", str(bare), "--json")
        self.assertEqual(code, cli.EXIT_CAPABILITY_UNAVAILABLE, output)
        self.assertEqual(json.loads(output)["verdict"], "unavailable")


class ValidatePlanCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CliFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_valid_plan_reports_its_items(self) -> None:
        self.fixture.write_plan()
        code, output = self.fixture.run_cli("validate-plan", str(self.fixture.plan_path), "--json")
        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        self.assertEqual([row["item_id"] for row in payload["items"]], ["item-01", "item-02"])
        self.assertTrue(payload["require_approval_before_run"])
        self.assertTrue(payload["require_human_labels"])
        self.assertRegex(payload["plan_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(payload["migration_notes"], ["migrated image batch 1.0.0 to 1.1.0"])

    def test_invalid_plan_exits_with_usage_error(self) -> None:
        self.fixture.write_plan(valid_plan(round=999))
        code, output = self.fixture.run_cli("validate-plan", str(self.fixture.plan_path), "--json")
        self.assertEqual(code, cli.EXIT_USAGE, output)
        self.assertTrue(json.loads(output)["errors"])


class QuoteCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CliFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_quote_reports_the_cost_shape_before_anything_runs(self) -> None:
        self.fixture.write_plan()
        code, output = self.fixture.run_cli("quote", str(self.fixture.plan_path), "--json")
        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        self.assertEqual(payload["image_count"], 2)
        self.assertTrue(payload["approval_required"])
        self.assertTrue(payload["require_human_labels"])
        self.assertRegex(payload["plan_sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(payload["spends_allowance_on_quote"])


class RunCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CliFixture()
        self.addCleanup(self.fixture.cleanup)
        self.fixture.write_plan()
        self.fixture.control()

    def run_batch(self, *extra: str) -> tuple[int, str]:
        return self.fixture.run_cli(
            "run",
            "--plan",
            str(self.fixture.plan_path),
            "--job",
            str(self.fixture.job_path),
            "--codex-bin",
            str(SHIM),
            *self.fixture.base_args(),
            "--json",
            *extra,
        )

    def test_run_without_approval_stops_before_spending(self) -> None:
        code, output = self.run_batch()
        self.assertEqual(code, cli.EXIT_APPROVAL_REQUIRED, output)
        ledger = json.loads(self.fixture.job_path.read_text(encoding="utf-8"))
        self.assertEqual(ledger["error_category"], "approval_required")
        self.assertEqual(len(list(self.fixture.generation_dir.rglob("*.png"))), 0)

    def test_approved_run_produces_receipts_and_completes(self) -> None:
        code, output = self.run_batch("--approve")
        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        self.assertEqual(len(payload["receipts"]), 2)
        ledger = json.loads(self.fixture.job_path.read_text(encoding="utf-8"))
        self.assertEqual(ledger["state"], "Completed")
        self.assertTrue(all(row["state"] == "Generated" for row in ledger["items"]))

    def test_receipts_verify_against_the_files_on_disk(self) -> None:
        _code, output = self.run_batch("--approve")
        receipts = json.loads(output)["receipts"]
        for receipt in receipts:
            published = self.fixture.destination / receipt["path"]
            self.assertTrue(published.is_file(), receipt["path"])

    def test_a_resumed_run_does_not_regenerate_finished_items(self) -> None:
        """The allowance is only spent once per item."""
        self.run_batch("--approve")
        before = len(list(self.fixture.generation_dir.rglob("*.png")))
        code, output = self.run_batch("--approve")
        self.assertEqual(code, 0, output)
        after = len(list(self.fixture.generation_dir.rglob("*.png")))
        self.assertEqual(before, after, "a resumed run must not call the generator again")
        self.assertEqual(json.loads(output)["receipts"], [])

    def test_usage_limit_stops_the_run_and_is_recorded(self) -> None:
        self.fixture.control(mode="usage_limit", resets_at=1_800_000_000)
        code, output = self.run_batch("--approve")
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        ledger = json.loads(self.fixture.job_path.read_text(encoding="utf-8"))
        self.assertEqual(ledger["error_category"], "quota_exceeded")
        self.assertEqual(ledger["usage_limit"]["limit_id"], "image_gen")
        self.assertEqual(ledger["usage_limit"]["resets_at"], 1_800_000_000)

    def test_usage_limit_does_not_attempt_the_remaining_items(self) -> None:
        self.fixture.control(mode="usage_limit")
        self.run_batch("--approve")
        attempts = len(list(self.fixture.base.glob("**/*last-message.txt")))
        self.assertEqual(attempts, 1, "the second item must not be attempted after the limit is hit")

    def test_missing_artifact_leaves_the_item_unresolved(self) -> None:
        """An exit code of zero without a file is not proof that nothing happened."""
        self.fixture.control(mode="silent")
        code, output = self.run_batch("--approve")
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        ledger = json.loads(self.fixture.job_path.read_text(encoding="utf-8"))
        self.assertEqual(ledger["state"], "Unknown")
        self.assertEqual(ledger["items"][0]["state"], "Unknown")

    def test_run_refuses_when_the_capability_probe_fails(self) -> None:
        bare = self.fixture.base / "bare-home"
        bare.mkdir()
        code, output = self.fixture.run_cli(
            "run",
            "--plan",
            str(self.fixture.plan_path),
            "--job",
            str(self.fixture.job_path),
            "--codex-bin",
            str(SHIM),
            "--codex-home",
            str(bare),
            "--generation-dir",
            str(self.fixture.generation_dir),
            "--destination",
            str(self.fixture.destination),
            "--approve",
            "--json",
        )
        self.assertEqual(code, cli.EXIT_CAPABILITY_UNAVAILABLE, output)

    def test_run_rejects_an_invalid_plan_before_writing_a_ledger(self) -> None:
        self.fixture.write_plan(valid_plan(items=[]))
        code, output = self.run_batch("--approve")
        self.assertEqual(code, cli.EXIT_USAGE, output)
        self.assertFalse(self.fixture.job_path.exists())


class StatusCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CliFixture()
        self.addCleanup(self.fixture.cleanup)
        self.fixture.write_plan()
        self.fixture.control()

    def test_status_reports_the_ledger_state(self) -> None:
        self.fixture.run_cli(
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
        code, output = self.fixture.run_cli("status", "--job", str(self.fixture.job_path), "--json")
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["state"], "Completed")

    def test_status_on_a_missing_ledger_is_an_error(self) -> None:
        code, _output = self.fixture.run_cli(
            "status", "--job", str(self.fixture.base / "absent.json"), "--json"
        )
        self.assertEqual(code, cli.EXIT_FAILURE)


class EvaluateAndOptimizeCommandTests(unittest.TestCase):
    """Evaluation and optimization are driven through the real handlers, not fakes."""

    def setUp(self) -> None:
        self.fixture = CliFixture()
        self.addCleanup(self.fixture.cleanup)
        self.fixture.write_plan()
        self.fixture.control()

    def test_a_labeled_passing_batch_is_accepted(self) -> None:
        """1.1.0 requires human labels, so "pass" is only reachable once they exist."""
        self.fixture.run_approved_batch()
        labels = self.fixture.base / "labels.json"
        labels.write_text(
            json.dumps({"item-01": "approved", "item-02": "approved"}), encoding="utf-8"
        )
        code, output = self.fixture.evaluate_batch("--labels", str(labels))
        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        self.assertEqual(payload["decision"], "pass")
        self.assertEqual(payload["state"], "Accepted")
        self.assertEqual(self.fixture.read_job()["state"], "Accepted")

    def test_the_recorded_evaluation_carries_the_scores_hash(self) -> None:
        self.fixture.run_approved_batch()
        _code, output = self.fixture.evaluate_batch()
        recorded = self.fixture.read_job()["evaluation"]
        self.assertEqual(recorded["scores_sha256"], json.loads(output)["scores_sha256"])
        self.assertRegex(recorded["scores_sha256"], r"^[0-9a-f]{64}$")

    def test_required_human_labels_cannot_pass_unlabeled(self) -> None:
        self.fixture.run_approved_batch()
        code, output = self.fixture.evaluate_batch()
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["decision"], "pending_approval")
        self.assertEqual(self.fixture.read_job()["state"], "PendingApproval")

    def test_whole_batch_approval_passes(self) -> None:
        self.fixture.run_approved_batch()
        labels = self.fixture.base / "labels.json"
        labels.write_text(json.dumps({"item-01": "approved", "item-02": "approved"}), encoding="utf-8")
        code, output = self.fixture.evaluate_batch("--labels", str(labels))
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["decision"], "pass")
        self.assertEqual(self.fixture.read_job()["state"], "Accepted")

    def test_partial_labels_stay_pending(self) -> None:
        self.fixture.run_approved_batch()
        labels = self.fixture.base / "labels.json"
        labels.write_text(json.dumps({"item-01": "approved"}), encoding="utf-8")
        code, output = self.fixture.evaluate_batch("--labels", str(labels))
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["decision"], "pending_approval")
        self.assertEqual(self.fixture.read_job()["state"], "PendingApproval")

    def test_one_rejection_fails_the_batch_despite_a_perfect_advisory_score(self) -> None:
        self.fixture.run_approved_batch()
        labels = self.fixture.base / "labels.json"
        labels.write_text(json.dumps({"item-01": "rejected", "item-02": "approved"}), encoding="utf-8")
        advisory = self.fixture.base / "advisory.json"
        advisory.write_text(json.dumps({"item-01": [1.0, "flawless"]}), encoding="utf-8")
        code, output = self.fixture.evaluate_batch("--labels", str(labels), "--advisory", str(advisory))
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertEqual(json.loads(output)["decision"], "fail")
        self.assertEqual(self.fixture.read_job()["state"], "Evaluated")

    def test_a_deterministic_failure_leaves_the_job_evaluated(self) -> None:
        self.fixture.control(mode="failure")
        self.fixture.run_approved_batch()
        code, output = self.fixture.evaluate_batch()
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertEqual(json.loads(output)["decision"], "fail")
        self.assertEqual(self.fixture.read_job()["state"], "Evaluated")

    def test_optimize_requires_a_job_argument(self) -> None:
        code, _output = self.fixture.run_cli(
            "optimize",
            "--plan",
            str(self.fixture.plan_path),
            "--scores",
            str(self.fixture.base / "scores.json"),
            "--out",
            str(self.fixture.base / "next.json"),
            "--json",
        )
        self.assertEqual(code, cli.EXIT_USAGE)

    def test_optimize_refuses_a_job_that_was_not_evaluated(self) -> None:
        self.fixture.run_approved_batch()
        code, output = self.fixture.run_cli(
            "optimize",
            "--plan",
            str(self.fixture.plan_path),
            "--job",
            str(self.fixture.job_path),
            "--scores",
            str(self.fixture.base / "scores.json"),
            "--out",
            str(self.fixture.base / "next.json"),
            "--json",
        )
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertEqual(json.loads(output)["error_category"], "recovery_required")

    def test_optimize_refuses_scores_that_are_not_the_recorded_ones(self) -> None:
        self.fixture.control(mode="failure")
        self.fixture.run_approved_batch()
        self.fixture.evaluate_batch()
        substitute = self.fixture.base / "substitute.json"
        substitute.write_text(json.dumps({"batch_id": "portrait-study"}), encoding="utf-8")
        code, output = self.fixture.run_cli(
            "optimize",
            "--plan",
            str(self.fixture.plan_path),
            "--job",
            str(self.fixture.job_path),
            "--scores",
            str(substitute),
            "--out",
            str(self.fixture.base / "next.json"),
            "--json",
        )
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertIn("not the ones recorded", json.loads(output)["error"])

    def test_optimize_writes_the_next_round_and_records_it(self) -> None:
        self.fixture.control(mode="failure")
        self.fixture.run_approved_batch()
        self.fixture.evaluate_batch()
        rewrites = self.fixture.base / "rewrites.json"
        rewrites.write_text(
            json.dumps({"item-01": "a calmer portrait", "item-02": "a calmer second portrait"}),
            encoding="utf-8",
        )
        next_plan = self.fixture.base / "next.json"
        code, output = self.fixture.run_cli(
            "optimize",
            "--plan",
            str(self.fixture.plan_path),
            "--job",
            str(self.fixture.job_path),
            "--scores",
            str(self.fixture.base / "scores.json"),
            "--rewrites",
            str(rewrites),
            "--out",
            str(next_plan),
            "--json",
        )
        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        self.assertEqual(payload["state"], "Optimized")
        document = json.loads(next_plan.read_text(encoding="utf-8"))
        self.assertEqual(document["schema_version"], "1.1.0")
        self.assertEqual(document["round"], 2)
        job = self.fixture.read_job()
        self.assertEqual(job["optimization"]["round"], 2)
        self.assertEqual(job["optimization"]["plan_hash"] if "plan_hash" in job["optimization"] else payload["plan_sha256"], payload["plan_sha256"])


class NoCertificateFilesTests(unittest.TestCase):
    def test_cli_module_exposes_stable_exit_codes(self) -> None:
        self.assertEqual(
            (
                cli.EXIT_OK,
                cli.EXIT_FAILURE,
                cli.EXIT_USAGE,
                cli.EXIT_APPROVAL_REQUIRED,
                cli.EXIT_CAPABILITY_UNAVAILABLE,
            ),
            (0, 1, 2, 3, 4),
        )


class JobContentionTests(unittest.TestCase):
    """A second writer must be refused before it can decide anything, let alone spend."""

    def setUp(self) -> None:
        self.fixture = CliFixture()
        self.addCleanup(self.fixture.cleanup)
        self.fixture.write_plan()
        self.fixture.control()

    def run_batch(self, *extra: str) -> tuple[int, str]:
        return self.fixture.run_cli(
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
            *extra,
        )

    def test_a_locked_job_refuses_the_run_and_spends_nothing(self) -> None:
        with job_lock.JobLock(self.fixture.job_path):
            code, output = self.run_batch()
        self.assertEqual(code, cli.EXIT_JOB_LOCKED, output)
        self.assertEqual(json.loads(output)["error_category"], "job_already_running")
        self.assertEqual(len(list(self.fixture.generation_dir.rglob("*.png"))), 0)
        self.assertFalse(self.fixture.job_path.exists())

    def test_a_locked_job_refuses_evaluate(self) -> None:
        with job_lock.JobLock(self.fixture.job_path):
            code, output = self.fixture.run_cli(
                "evaluate",
                "--plan",
                str(self.fixture.plan_path),
                "--job",
                str(self.fixture.job_path),
                "--scores",
                str(self.fixture.base / "scores.json"),
                *self.fixture.base_args(),
                "--json",
            )
        self.assertEqual(code, cli.EXIT_JOB_LOCKED, output)
        self.assertFalse((self.fixture.base / "scores.json").exists())

    def test_the_job_is_runnable_again_once_the_lock_is_released(self) -> None:
        with job_lock.JobLock(self.fixture.job_path):
            self.assertEqual(self.run_batch()[0], cli.EXIT_JOB_LOCKED)
        code, output = self.run_batch()
        self.assertEqual(code, 0, output)

    def test_contention_exit_codes_are_distinct(self) -> None:
        self.assertEqual(
            (cli.EXIT_JOB_LOCKED, cli.EXIT_RECOVERY_REQUIRED), (5, 6)
        )


class ApprovalBindingCliTests(unittest.TestCase):
    """The approval a run records must describe exactly the work it is about to do."""

    def setUp(self) -> None:
        self.fixture = CliFixture()
        self.addCleanup(self.fixture.cleanup)
        self.invocations = self.fixture.base / "invocations"
        self.invocations.mkdir()
        self.reference = self.fixture.base / "references" / "style.png"
        self.reference.parent.mkdir()
        shutil.copyfile(REAL_PNG, self.reference)
        self.fixture.write_plan(
            valid_plan(
                items=[
                    {"id": "item-01", "prompt": "a calm portrait", "reference_images": [str(self.reference)]},
                    {"id": "item-02", "prompt": "a second portrait"},
                ]
            )
        )
        self.fixture.control(invocation_dir=str(self.invocations))

    def run_batch(self, *extra: str) -> tuple[int, str]:
        return self.fixture.run_cli(
            "run",
            "--plan",
            str(self.fixture.plan_path),
            "--job",
            str(self.fixture.job_path),
            "--codex-bin",
            str(SHIM),
            *self.fixture.base_args(),
            "--json",
            *extra,
        )

    def declared_hash(self) -> str:
        _code, output = self.fixture.run_cli(
            "quote", str(self.fixture.plan_path), "--json"
        )
        return json.loads(output)["plan_sha256"]

    def ledger(self) -> dict:
        return json.loads(self.fixture.job_path.read_text(encoding="utf-8"))

    def invoked(self) -> list:
        return sorted(self.invocations.glob("*.json"))

    def test_approval_is_bound_to_the_declared_plan_and_remaining_count(self) -> None:
        code, output = self.run_batch("--approve")
        self.assertEqual(code, 0, output)
        current = self.ledger()["approval"]["current"]
        self.assertEqual(current["plan_hash"], self.declared_hash())
        self.assertEqual(current["round"], 1)
        self.assertEqual(current["remaining_count"], 2)
        self.assertEqual(len(self.invoked()), 2)

    def test_the_approval_precedes_spending(self) -> None:
        """A refusal must leave no invocation behind, which only holds if the gate is first."""
        code, output = self.run_batch()
        self.assertEqual(code, cli.EXIT_APPROVAL_REQUIRED, output)
        self.assertEqual(self.invoked(), [])
        self.assertIsNone(self.ledger()["approval"]["current"])
        self.assertEqual(self.ledger()["error_category"], "approval_required")

    def test_a_settled_job_refuses_a_new_plan_and_reuses_no_approval(self) -> None:
        """An approval authorizes the work it named, so a different plan needs a new cycle.

        A completed job also cannot simply be re-run: an unfinished or settled
        transaction is reconciled by `recover`, never by a silent second run.
        """
        self.run_batch("--approve")
        recorded = self.ledger()["approval"]["current"]
        self.assertEqual(len(self.invoked()), 2)

        self.fixture.write_plan(
            valid_plan(round=2, items=[{"id": "item-03", "prompt": "a third portrait"}])
        )
        code, output = self.run_batch("--approve")
        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED, output)
        self.assertEqual(len(self.invoked()), 2, "a refused run must invoke nothing")
        self.assertEqual(self.ledger()["approval"]["current"], recorded)

    def test_the_ledger_records_neither_prompts_nor_reference_paths(self) -> None:
        self.run_batch("--approve")
        stored = self.fixture.job_path.read_text(encoding="utf-8")
        self.assertNotIn("a calm portrait", stored)
        self.assertNotIn(str(self.reference), stored)
        self.assertNotIn(str(self.fixture.base), stored)


if __name__ == "__main__":
    unittest.main()
