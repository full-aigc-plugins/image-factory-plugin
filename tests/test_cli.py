import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import image_factory_cli as cli  # noqa: E402
import job_lock  # noqa: E402


FAKE = ROOT / "tests" / "fakes" / "fake_codex.py"
REAL_PNG = ROOT / "assets" / "logo.png"


def fast_python() -> str:
    candidate = Path(sys.base_prefix) / "bin" / "python3"
    return str(candidate) if candidate.is_file() else sys.executable


def build_shim(platform_name: str | None = None) -> Path:
    directory = Path(tempfile.mkdtemp(prefix="image-factory-cli-shim-"))
    selected_platform = os.name if platform_name is None else platform_name
    if selected_platform == "nt":
        shim = directory / "codex.cmd"
        shim.write_text(f'@"{fast_python()}" "{FAKE}" %*\n', encoding="utf-8")
    else:
        shim = directory / "codex"
        shim.write_text(f'#!/bin/sh\nexec "{fast_python()}" "{FAKE}" "$@"\n', encoding="utf-8")
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return shim


SHIM = build_shim()


class PortableShimTests(unittest.TestCase):
    def test_windows_shim_uses_cmd_launcher_syntax(self) -> None:
        shim = build_shim(platform_name="nt")
        self.addCleanup(shutil.rmtree, shim.parent)
        self.assertEqual(shim.suffix, ".cmd")
        self.assertIn("%*", shim.read_text(encoding="utf-8"))

    def test_shim_uses_the_platform_launcher_and_forwards_arguments(self) -> None:
        expected_suffix = ".cmd" if os.name == "nt" else ""
        self.assertEqual(SHIM.suffix, expected_suffix)

        with tempfile.TemporaryDirectory() as directory:
            control_path = Path(directory) / "control.json"
            control_path.write_text(json.dumps({"mode": "success"}), encoding="utf-8")
            environment = os.environ.copy()
            environment["FAKE_CODEX_CONTROL"] = str(control_path)
            result = subprocess.run(
                [str(SHIM), "exec", "portable-check"],
                capture_output=True,
                text=True,
                env=environment,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            invocation = json.loads(
                (control_path.parent / "fake-codex-argv.json").read_text(encoding="utf-8")
            )
            self.assertEqual(invocation["argv"], ["exec", "portable-check"])


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

    def base_args(self) -> list[str]:
        return [
            "--codex-home",
            str(self.codex_home),
            "--generation-dir",
            str(self.generation_dir),
            "--destination",
            str(self.destination),
        ]

    def run_approved_batch(self) -> dict:
        code, output = self.run_cli(
            "run", "--plan", str(self.plan_path), "--job", str(self.job_path),
            "--codex-bin", str(SHIM), *self.base_args(), "--approve", "--json",
        )
        if code != cli.EXIT_OK:
            raise AssertionError(output)
        return json.loads(output)

    def evaluate_without_labels(self) -> tuple[int, dict]:
        code, output = self.run_cli(
            "evaluate", "--plan", str(self.plan_path), "--job", str(self.job_path),
            "--scores", str(self.base / "scores.json"), *self.base_args(), "--json",
        )
        return code, json.loads(output)

    def read_job(self) -> dict:
        return json.loads(self.job_path.read_text(encoding="utf-8"))

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
        self.assertRegex(payload["plan_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(payload["require_human_labels"])
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
        self.assertFalse(payload["spends_allowance_on_quote"])
        self.assertRegex(payload["plan_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(payload["require_human_labels"])
        self.assertEqual(payload["migration_notes"], ["migrated image batch 1.0.0 to 1.1.0"])
        self.assertFalse(self.fixture.job_path.exists())


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

    def test_run_rejects_non_positive_and_non_finite_timeouts_before_writing_a_job(self) -> None:
        for value in ("0", "-1", "nan", "inf", "-inf"):
            with self.subTest(timeout=value):
                job_path = self.fixture.base / f"job-{value}.json"
                code, output = self.fixture.run_cli(
                    "run", "--plan", str(self.fixture.plan_path), "--job", str(job_path),
                    "--codex-bin", str(SHIM), *self.fixture.base_args(), "--approve",
                    f"--timeout={value}", "--json",
                )
                self.assertEqual(code, cli.EXIT_USAGE, output)
                self.assertFalse(job_path.exists())
        self.assertEqual(len(list(self.fixture.generation_dir.rglob("*.png"))), 0)
        self.assertFalse((self.fixture.base / "fake-codex-argv.json").exists())

    def test_approval_is_bound_before_the_first_invocation_without_plan_secrets(self) -> None:
        validated, _ = cli._validated_plan(
            type("Args", (), {"plan": str(self.fixture.plan_path)})()
        )
        original = cli.generation_runner.run_item

        def assert_binding(**kwargs):
            ledger = json.loads(self.fixture.job_path.read_text(encoding="utf-8"))
            current = ledger["approval"]["current"]
            self.assertEqual(current["plan_sha256"], validated.plan_sha256)
            self.assertEqual(current["round"], validated.round)
            self.assertEqual(current["image_count"], 2)
            serialized = json.dumps(ledger)
            self.assertNotIn("a calm portrait", serialized)
            self.assertNotIn("reference_images", serialized)
            return original(**kwargs)

        with patch.object(cli.generation_runner, "run_item", side_effect=assert_binding):
            code, output = self.run_batch("--approve")
        self.assertEqual(code, cli.EXIT_OK, output)

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

    def test_resumed_legacy_manifest_keeps_prior_receipts_when_one_item_is_added(self) -> None:
        code, output = self.run_batch("--approve")
        self.assertEqual(code, 0, output)
        legacy_manifest = Path(str(self.fixture.job_path) + ".receipts.json")
        prior = json.loads(legacy_manifest.read_text(encoding="utf-8"))
        shutil.rmtree(Path(str(self.fixture.job_path) + ".receipts"))

        ledger = json.loads(self.fixture.job_path.read_text(encoding="utf-8"))
        ledger["state"] = "Partial"
        self.fixture.job_path.write_text(json.dumps(ledger), encoding="utf-8")

        plan = valid_plan()
        plan["items"].append({"id": "item-03", "prompt": "a third portrait"})
        self.fixture.write_plan(plan)
        code, output = self.run_batch("--approve")

        self.assertEqual(code, 0, output)
        ledger = json.loads(self.fixture.job_path.read_text(encoding="utf-8"))
        self.assertEqual(len(ledger["approval"]["history"]), 2)
        self.assertEqual(ledger["approval"]["current"]["image_count"], 1)
        rebuilt = json.loads(legacy_manifest.read_text(encoding="utf-8"))
        self.assertEqual(
            [receipt["item_id"] for receipt in rebuilt],
            [receipt["item_id"] for receipt in prior] + ["item-03"],
        )

        before = len(list(self.fixture.generation_dir.rglob("*.png")))
        code, output = self.run_batch("--approve")
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["receipts"], [])
        self.assertEqual(before, len(list(self.fixture.generation_dir.rglob("*.png"))))

    def test_changed_completed_job_is_refused_without_generation(self) -> None:
        code, output = self.run_batch("--approve")
        self.assertEqual(code, 0, output)
        before = len(list(self.fixture.generation_dir.rglob("*.png")))

        plan = valid_plan()
        plan["items"].append({"id": "item-03", "prompt": "a third portrait"})
        self.fixture.write_plan(plan)
        code, output = self.run_batch("--approve")

        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED, output)
        self.assertEqual(json.loads(output)["error_category"], "recovery_required")
        after = len(list(self.fixture.generation_dir.rglob("*.png")))
        self.assertEqual(before, after)

    def test_changed_completed_metadata_is_refused_even_when_no_item_is_pending(self) -> None:
        code, output = self.run_batch("--approve")
        self.assertEqual(code, 0, output)
        before = len(list(self.fixture.generation_dir.rglob("*.png")))

        plan = valid_plan()
        plan["judge_policy"]["pass_threshold"] = 0.9
        self.fixture.write_plan(plan)
        code, output = self.run_batch("--approve")

        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED, output)
        self.assertEqual(json.loads(output)["error_category"], "recovery_required")
        self.assertEqual(before, len(list(self.fixture.generation_dir.rglob("*.png"))))

    def test_partial_with_zero_pending_is_refused_without_generation(self) -> None:
        code, output = self.run_batch("--approve")
        self.assertEqual(code, 0, output)
        ledger = json.loads(self.fixture.job_path.read_text(encoding="utf-8"))
        ledger["state"] = "Partial"
        self.fixture.job_path.write_text(json.dumps(ledger), encoding="utf-8")
        before = len(list(self.fixture.generation_dir.rglob("*.png")))

        code, output = self.run_batch("--approve")

        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED, output)
        self.assertEqual(json.loads(output)["error_category"], "recovery_required")
        self.assertEqual(before, len(list(self.fixture.generation_dir.rglob("*.png"))))

    def test_partial_with_unknown_and_new_item_is_refused_without_generation(self) -> None:
        code, output = self.run_batch("--approve")
        self.assertEqual(code, 0, output)
        ledger = json.loads(self.fixture.job_path.read_text(encoding="utf-8"))
        ledger["state"] = "Partial"
        ledger["items"][0]["state"] = "Unknown"
        ledger["items"][0]["error_category"] = "unknown"
        self.fixture.job_path.write_text(json.dumps(ledger), encoding="utf-8")
        plan = valid_plan()
        plan["items"].append({"id": "item-03", "prompt": "a third portrait"})
        self.fixture.write_plan(plan)
        before = len(list(self.fixture.generation_dir.rglob("*.png")))

        code, output = self.run_batch("--approve")

        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED, output)
        self.assertEqual(json.loads(output)["error_category"], "recovery_required")
        self.assertEqual(before, len(list(self.fixture.generation_dir.rglob("*.png"))))

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

    def test_missing_artifact_is_recorded_as_an_unknown_item(self) -> None:
        self.fixture.control(mode="silent")
        code, output = self.run_batch("--approve")
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        ledger = json.loads(self.fixture.job_path.read_text(encoding="utf-8"))
        self.assertEqual(ledger["state"], "Unknown")
        self.assertEqual(ledger["items"][0]["error_category"], "unknown")

    @unittest.skipIf(os.name == "nt", "negative signal return codes are a Unix contract")
    def test_signal_interruption_becomes_unknown_and_stops_later_items(self) -> None:
        invocation_dir = self.fixture.base / "signal-invocations"
        self.fixture.control(mode="signal", invocation_dir=str(invocation_dir))
        code, output = self.run_batch("--approve")
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        ledger = json.loads(self.fixture.job_path.read_text(encoding="utf-8"))
        self.assertEqual(ledger["state"], "Unknown")
        self.assertEqual(ledger["items"][0]["state"], "Unknown")
        self.assertEqual(len(list(invocation_dir.glob("*.json"))), 1)

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

    def test_run_refuses_an_active_job_without_spending_a_call(self) -> None:
        with job_lock.JobLock(self.fixture.job_path):
            code, output = self.run_batch("--approve")

        self.assertEqual(code, 5, output)
        self.assertEqual(json.loads(output)["error_category"], "job_already_running")
        self.assertEqual(len(list(self.fixture.generation_dir.rglob("*.png"))), 0)


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

    def test_status_reports_summaries_without_sensitive_content(self) -> None:
        self.fixture.run_approved_batch()
        code, output = self.fixture.run_cli("status", "--job", str(self.fixture.job_path), "--json")
        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        self.assertEqual(payload["batch"]["round"], 1)
        self.assertEqual(payload["approval"]["history_count"], 1)
        self.assertEqual(payload["counts"]["generated"], 2)
        self.assertNotIn("items", payload)
        self.assertNotIn("history", payload["approval"])

    def test_status_counts_every_item_state_and_conserves_the_bound_total(self) -> None:
        self.fixture.run_approved_batch()
        ledger = self.fixture.read_job()
        template = ledger["items"][0]
        states = ("Generated", "Failed", "Pending", "Unknown", "Attempting", "Skipped")
        ledger["items"] = []
        for index, state in enumerate(states, start=1):
            row = dict(template)
            row.update(
                item_id=f"item-{index:02d}",
                state=state,
                idempotency_key=f"{index:064x}",
                receipt_id="receipt" if state == "Generated" else None,
                error_category="unknown" if state == "Unknown" else None,
            )
            ledger["items"].append(row)
        ledger["current_item_keys"] = [row["idempotency_key"] for row in ledger["items"]]
        ledger["batch"]["image_count"] = len(states)
        cli.job_ledger.write_ledger(self.fixture.job_path, ledger)

        code, output = self.fixture.run_cli("status", "--job", str(self.fixture.job_path), "--json")

        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        self.assertEqual(
            payload["counts"],
            {"attempting": 1, "failed": 1, "generated": 1, "pending": 1, "skipped": 1, "unknown": 1},
        )
        self.assertEqual(sum(payload["counts"].values()), payload["batch"]["image_count"])
        self.assertNotIn("items", payload)

    def test_status_on_a_missing_ledger_is_an_error(self) -> None:
        code, _output = self.fixture.run_cli(
            "status", "--job", str(self.fixture.base / "absent.json"), "--json"
        )
        self.assertEqual(code, cli.EXIT_FAILURE)

    def test_status_refuses_duplicate_current_round_rows_instead_of_overcounting(self) -> None:
        self.fixture.run_approved_batch()
        ledger = self.fixture.read_job()
        ledger["items"].append(dict(ledger["items"][0]))
        cli.job_ledger.write_ledger(self.fixture.job_path, ledger)

        code, output = self.fixture.run_cli("status", "--job", str(self.fixture.job_path), "--json")

        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertIn("duplicate current-round", json.loads(output)["error"])


class EvaluateAndOptimizeCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CliFixture()
        self.addCleanup(self.fixture.cleanup)
        self.fixture.write_plan()
        self.fixture.control()
        self.scores_path = self.fixture.base / "scores.json"
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

    def persist_failing_evaluation(self) -> None:
        failing = {
            "schema_version": "1.0.0", "batch_id": "portrait-study", "round": 1,
            "pass_threshold": 0.8,
            "deterministic_gates": {
                "all_passed": False,
                "per_item": [
                    {"item_id": "item-01", "passed": False, "failures": ["not_a_png"]},
                    {"item_id": "item-02", "passed": True, "failures": []},
                ],
            },
            "advisory": {"enabled": False, "items": []},
            "human_labels": [
                {"item_id": "item-01", "label": "unlabeled", "at": None},
                {"item_id": "item-02", "label": "unlabeled", "at": None},
            ],
            "decision": "fail",
        }
        cli.atomic_json.write_json_atomic(self.scores_path, failing)
        ledger = cli.job_ledger.JobLedger(self.fixture.job_path)
        ledger.record_evaluation(hashlib.sha256(self.scores_path.read_bytes()).hexdigest(), "fail")

    def replace_scores_evidence(self, scores: object) -> None:
        cli.atomic_json.write_json_atomic(self.scores_path, scores)
        ledger = self.fixture.read_job()
        ledger["evaluation"]["scores_sha256"] = hashlib.sha256(self.scores_path.read_bytes()).hexdigest()
        cli.job_ledger.write_ledger(self.fixture.job_path, ledger)

    def optimize(self, out_path: Path | None = None, rewrites: Path | None = None) -> tuple[int, str]:
        arguments = [
            "optimize", "--job", str(self.fixture.job_path), "--plan", str(self.fixture.plan_path),
            "--scores", str(self.scores_path), "--out", str(out_path or self.fixture.base / "next.json"),
            "--json",
        ]
        if rewrites is not None:
            arguments.extend(("--rewrites", str(rewrites)))
        return self.fixture.run_cli(*arguments)

    def test_evaluate_writes_a_scores_document(self) -> None:
        code, output = self.fixture.run_cli(
            "evaluate",
            "--plan",
            str(self.fixture.plan_path),
            "--job",
            str(self.fixture.job_path),
            "--scores",
            str(self.scores_path),
            *self.fixture.base_args(),
            "--json",
        )
        self.assertEqual(code, 0, output)
        scores = json.loads(self.scores_path.read_text(encoding="utf-8"))
        self.assertEqual(scores["decision"], "pending_approval")
        self.assertTrue(scores["deterministic_gates"]["all_passed"])
        ledger = self.fixture.read_job()
        self.assertEqual(ledger["state"], "PendingApproval")
        self.assertEqual(ledger["evaluation"]["scores_sha256"], hashlib.sha256(self.scores_path.read_bytes()).hexdigest())

    def test_required_human_labels_cannot_pass_unlabeled(self) -> None:
        code, payload = self.fixture.evaluate_without_labels()
        self.assertEqual(code, 0)
        self.assertEqual(payload["decision"], "pending_approval")
        self.assertEqual(self.fixture.read_job()["state"], "PendingApproval")

    def test_failed_scores_write_preserves_the_previous_file_and_job_state(self) -> None:
        self.scores_path.write_text('{"previous": true}\n', encoding="utf-8")
        before = self.scores_path.read_bytes()
        with patch("atomic_json.json.dump", side_effect=OSError("injected write failure")):
            code, output = self.fixture.run_cli(
                "evaluate", "--plan", str(self.fixture.plan_path),
                "--job", str(self.fixture.job_path), "--scores", str(self.scores_path),
                *self.fixture.base_args(), "--json",
            )
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertEqual(self.scores_path.read_bytes(), before)
        self.assertEqual(self.fixture.read_job()["state"], "Completed")
        self.assertEqual(list(self.fixture.base.glob(".atomic-*.tmp")), [])

    def test_whole_batch_approval_accepts_the_job(self) -> None:
        labels = self.fixture.base / "labels.json"
        labels.write_text(json.dumps({"item-01": "approved", "item-02": "approved"}), encoding="utf-8")
        code, output = self.fixture.run_cli(
            "evaluate", "--plan", str(self.fixture.plan_path), "--job", str(self.fixture.job_path),
            "--scores", str(self.scores_path), "--labels", str(labels), *self.fixture.base_args(), "--json",
        )
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["decision"], "pass")
        self.assertEqual(self.fixture.read_job()["state"], "Accepted")

    def test_partial_labels_remain_pending(self) -> None:
        labels = self.fixture.base / "labels.json"
        labels.write_text(json.dumps({"item-01": "approved"}), encoding="utf-8")
        code, output = self.fixture.run_cli(
            "evaluate", "--plan", str(self.fixture.plan_path), "--job", str(self.fixture.job_path),
            "--scores", str(self.scores_path), "--labels", str(labels), *self.fixture.base_args(), "--json",
        )
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["decision"], "pending_approval")
        self.assertEqual(self.fixture.read_job()["state"], "PendingApproval")

    def test_rejection_fails_despite_perfect_advisory_score(self) -> None:
        labels = self.fixture.base / "labels.json"
        advisory = self.fixture.base / "advisory.json"
        labels.write_text(json.dumps({"item-01": "rejected", "item-02": "approved"}), encoding="utf-8")
        advisory.write_text(json.dumps({"item-01": [1.0, "perfect"], "item-02": [1.0, "perfect"]}), encoding="utf-8")
        code, output = self.fixture.run_cli(
            "evaluate", "--plan", str(self.fixture.plan_path), "--job", str(self.fixture.job_path),
            "--scores", str(self.scores_path), "--labels", str(labels), "--advisory", str(advisory),
            *self.fixture.base_args(), "--json",
        )
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertEqual(json.loads(output)["decision"], "fail")
        self.assertEqual(self.fixture.read_job()["state"], "Evaluated")

    def test_optimize_requires_job_argument(self) -> None:
        self.fixture.run_cli(
            "evaluate",
            "--plan",
            str(self.fixture.plan_path),
            "--job",
            str(self.fixture.job_path),
            "--scores",
            str(self.scores_path),
            *self.fixture.base_args(),
            "--json",
        )
        next_plan = self.fixture.base / "next.json"
        code, output = self.fixture.run_cli(
            "optimize",
            "--plan",
            str(self.fixture.plan_path),
            "--scores",
            str(self.scores_path),
            "--out",
            str(next_plan),
            "--json",
        )
        self.assertEqual(code, cli.EXIT_USAGE, output)
        self.assertFalse(next_plan.exists())

    def test_optimize_requires_an_instruction_for_each_item_needing_rework(self) -> None:
        self.persist_failing_evaluation()
        code, output = self.fixture.run_cli(
            "optimize",
            "--job",
            str(self.fixture.job_path),
            "--plan",
            str(self.fixture.plan_path),
            "--scores",
            str(self.scores_path),
            "--out",
            str(self.fixture.base / "next.json"),
            "--json",
        )
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertEqual(json.loads(output)["errors"][0]["code"], "optimizer_missing_instruction")

    def test_optimize_with_a_rewrite_writes_the_next_round(self) -> None:
        self.persist_failing_evaluation()
        rewrites = self.fixture.base / "rewrites.json"
        rewrites.write_text(json.dumps({"item-01": "a calmer portrait"}), encoding="utf-8")
        next_plan = self.fixture.base / "next.json"
        code, output = self.fixture.run_cli(
            "optimize",
            "--job",
            str(self.fixture.job_path),
            "--plan",
            str(self.fixture.plan_path),
            "--scores",
            str(self.scores_path),
            "--rewrites",
            str(rewrites),
            "--out",
            str(next_plan),
            "--json",
        )
        self.assertEqual(code, 0, output)
        document = json.loads(next_plan.read_text(encoding="utf-8"))
        self.assertEqual(document["round"], 2)
        self.assertEqual(document["items"], [{"id": "item-01", "prompt": "a calmer portrait"}])
        ledger = self.fixture.read_job()
        self.assertEqual(ledger["state"], "Optimized")
        self.assertEqual(ledger["optimization"]["next_plan_sha256"], cli.plan_validator.validate_plan(document, base_dir=next_plan.parent).plan_sha256)
        self.assertIsNone(ledger["approval"]["current"])

    def test_optimize_uses_the_exact_job_lock(self) -> None:
        with job_lock.JobLock(self.fixture.job_path):
            code, output = self.fixture.run_cli(
                "optimize", "--job", str(self.fixture.job_path), "--plan", str(self.fixture.plan_path),
                "--scores", str(self.scores_path), "--out", str(self.fixture.base / "next.json"), "--json",
            )
        self.assertEqual(code, cli.EXIT_JOB_LOCKED, output)
        self.assertEqual(json.loads(output)["error_category"], "job_already_running")

    def test_optimize_refuses_a_scores_file_that_changed_after_evaluation(self) -> None:
        self.persist_failing_evaluation()
        self.scores_path.write_text(self.scores_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        next_plan = self.fixture.base / "next.json"
        code, output = self.fixture.run_cli(
            "optimize", "--job", str(self.fixture.job_path), "--plan", str(self.fixture.plan_path),
            "--scores", str(self.scores_path), "--out", str(next_plan), "--json",
        )
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertIn("scores file does not match", json.loads(output)["error"])
        self.assertFalse(next_plan.exists())

    def test_optimize_refuses_a_plan_that_does_not_match_the_job(self) -> None:
        self.persist_failing_evaluation()
        changed = valid_plan()
        changed["items"][0]["prompt"] = "changed after evaluation"
        self.fixture.write_plan(changed)
        code, output = self.fixture.run_cli(
            "optimize", "--job", str(self.fixture.job_path), "--plan", str(self.fixture.plan_path),
            "--scores", str(self.scores_path), "--out", str(self.fixture.base / "next.json"), "--json",
        )
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertIn("plan does not match", json.loads(output)["error"])

    def test_optimize_refuses_scores_for_a_different_round(self) -> None:
        self.persist_failing_evaluation()
        scores = json.loads(self.scores_path.read_text(encoding="utf-8"))
        scores["round"] = 2
        cli.atomic_json.write_json_atomic(self.scores_path, scores)
        ledger = self.fixture.read_job()
        ledger["evaluation"]["scores_sha256"] = hashlib.sha256(self.scores_path.read_bytes()).hexdigest()
        cli.job_ledger.write_ledger(self.fixture.job_path, ledger)
        code, output = self.fixture.run_cli(
            "optimize", "--job", str(self.fixture.job_path), "--plan", str(self.fixture.plan_path),
            "--scores", str(self.scores_path), "--out", str(self.fixture.base / "next.json"), "--json",
        )
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertIn("batch and round", json.loads(output)["error"])

    def test_optimize_validates_next_plan_before_replacing_existing_output(self) -> None:
        self.persist_failing_evaluation()
        rewrites = self.fixture.base / "rewrites.json"
        rewrites.write_text(json.dumps({"item-01": "x" * 20_001}), encoding="utf-8")
        next_plan = self.fixture.base / "next.json"
        next_plan.write_bytes(b"existing output must survive\n")
        before = next_plan.read_bytes()

        code, output = self.optimize(next_plan, rewrites)

        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertTrue(json.loads(output)["errors"])
        self.assertEqual(next_plan.read_bytes(), before)
        self.assertEqual(self.fixture.read_job()["state"], "Evaluated")

    def test_optimize_refuses_schema_invalid_scores(self) -> None:
        self.persist_failing_evaluation()
        scores = json.loads(self.scores_path.read_text(encoding="utf-8"))
        scores.pop("deterministic_gates")
        self.replace_scores_evidence(scores)
        code, output = self.optimize()
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertIn("scores schema invalid", json.loads(output)["error"])

    def test_optimize_refuses_missing_item_rows(self) -> None:
        self.persist_failing_evaluation()
        scores = json.loads(self.scores_path.read_text(encoding="utf-8"))
        scores["deterministic_gates"]["per_item"] = scores["deterministic_gates"]["per_item"][:1]
        self.replace_scores_evidence(scores)
        code, output = self.optimize()
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertIn("exactly one deterministic row", json.loads(output)["error"])

    def test_optimize_refuses_duplicate_item_rows(self) -> None:
        self.persist_failing_evaluation()
        scores = json.loads(self.scores_path.read_text(encoding="utf-8"))
        rows = scores["deterministic_gates"]["per_item"]
        scores["deterministic_gates"]["per_item"] = rows + [rows[0]]
        self.replace_scores_evidence(scores)
        code, output = self.optimize()
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertIn("exactly one deterministic row", json.loads(output)["error"])

    def test_optimize_refuses_decision_mismatch_with_ledger(self) -> None:
        self.persist_failing_evaluation()
        scores = json.loads(self.scores_path.read_text(encoding="utf-8"))
        scores["decision"] = "pass"
        self.replace_scores_evidence(scores)
        code, output = self.optimize()
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertIn("decision does not match", json.loads(output)["error"])


class NoCertificateFilesTests(unittest.TestCase):
    def test_cli_module_exposes_stable_exit_codes(self) -> None:
        self.assertEqual(
            (
                cli.EXIT_OK,
                cli.EXIT_FAILURE,
                cli.EXIT_USAGE,
                cli.EXIT_APPROVAL_REQUIRED,
                cli.EXIT_CAPABILITY_UNAVAILABLE,
                cli.EXIT_JOB_LOCKED,
                cli.EXIT_RECOVERY_REQUIRED,
            ),
            (0, 1, 2, 3, 4, 5, 6),
        )


if __name__ == "__main__":
    unittest.main()
