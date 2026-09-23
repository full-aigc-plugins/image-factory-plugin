import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import runtime_acceptance  # noqa: E402
import schema_lite  # noqa: E402
import image_factory_cli  # noqa: E402


class RuntimeAcceptanceTests(unittest.TestCase):
    def test_seed_matrix_keeps_paid_cross_host_and_fault_cases_not_run(self) -> None:
        matrix = runtime_acceptance.new_matrix(plugin_version="0.8.0")
        cases = {case["case_id"]: case for case in matrix["cases"]}
        for case_id in ("paid-4", "paid-8", "paid-12", "host-codex", "host-zcode", "host-kimi", "fault-interruption", "fault-duplicate-callback", "fault-concurrency", "fault-disk-full", "fault-quota-exhaustion"):
            self.assertEqual(cases[case_id]["status"], "NOT_RUN")
            self.assertEqual(cases[case_id]["evidence_refs"], [])
        schema = json.loads((ROOT / "schemas/runtime_acceptance_matrix.schema.json").read_text())
        self.assertEqual(schema_lite.validate(matrix, schema), [])

    def test_checked_in_matrix_has_no_synthetic_pass_claim(self) -> None:
        matrix = json.loads((ROOT / "data/benchmarks/runtime-acceptance-matrix.json").read_text())
        runtime_acceptance.validate_matrix(matrix)
        self.assertEqual(matrix["plugin_version"], "0.8.0")
        self.assertEqual(len(matrix["cases"]), 11)
        self.assertTrue(all(case["status"] == "NOT_RUN" for case in matrix["cases"]))

    def test_pass_requires_live_evidence_and_fault_proof(self) -> None:
        matrix = runtime_acceptance.new_matrix(plugin_version="0.8.0")
        record = {"status": "PASS", "started_at": "2026-09-23T01:00:00Z", "ended_at": "2026-09-23T01:05:00Z", "host": "Codex", "evidence_tier": "synthetic", "evidence_refs": ["tests/test_runtime_acceptance.py"]}
        with self.assertRaisesRegex(ValueError, "live_runtime"):
            runtime_acceptance.record_case(matrix, "paid-4", record)
        record["evidence_tier"] = "live_runtime"
        with self.assertRaisesRegex(ValueError, "story_proof"):
            runtime_acceptance.record_case(matrix, "paid-4", record)
        with self.assertRaisesRegex(ValueError, "fault_proof"):
            runtime_acceptance.record_case(matrix, "fault-disk-full", record)
        self.assertTrue(all(case["status"] == "NOT_RUN" for case in matrix["cases"]))

    def test_host_results_are_isolated(self) -> None:
        matrix = runtime_acceptance.new_matrix(plugin_version="0.8.0")
        updated = runtime_acceptance.record_case(matrix, "host-codex", {
            "status": "PASS", "started_at": "2026-09-23T01:00:00Z", "ended_at": "2026-09-23T01:05:00Z",
            "host": "Codex", "model": "observed-model", "provider": "observed-provider",
            "evidence_tier": "live_runtime", "evidence_refs": ["receipts/codex.json"],
        })
        cases = {case["case_id"]: case for case in updated["cases"]}
        self.assertEqual(cases["host-codex"]["status"], "PASS")
        self.assertEqual(cases["host-kimi"]["status"], "NOT_RUN")
        self.assertEqual(cases["host-zcode"]["status"], "NOT_RUN")
        self.assertEqual(schema_lite.validate(updated, json.loads((ROOT / "schemas/runtime_acceptance_matrix.schema.json").read_text())), [])

    def test_each_model_combination_gets_its_own_not_run_case(self) -> None:
        matrix = runtime_acceptance.new_matrix(plugin_version="0.8.0")
        updated = runtime_acceptance.add_case(matrix, case_id="model-codex-provider-a", kind="model_comparison", host="Codex", model="model-a", provider="provider-a", prompt_strategy="story-state-v1")
        cases = {case["case_id"]: case for case in updated["cases"]}
        self.assertEqual(cases["model-codex-provider-a"]["status"], "NOT_RUN")
        self.assertIsNone(cases["model-codex-provider-a"]["started_at"])
        self.assertEqual(cases["host-codex"]["status"], "NOT_RUN")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            runtime_acceptance.add_case(updated, case_id="model-codex-provider-a", kind="model_comparison", host="Codex")

    def test_semantic_validation_rejects_a_manually_forged_pass(self) -> None:
        matrix = runtime_acceptance.new_matrix(plugin_version="0.8.0")
        matrix["cases"][0]["status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "live_runtime"):
            runtime_acceptance.validate_matrix(matrix)

    def test_paid_pass_requires_all_shots_labeled_and_receipted(self) -> None:
        matrix = runtime_acceptance.new_matrix(plugin_version="0.8.0")
        record = {
            "status": "PASS", "started_at": "2026-09-23T01:00:00Z", "ended_at": "2026-09-23T01:05:00Z",
            "evidence_tier": "live_runtime", "evidence_refs": ["report.json"],
            "story_proof": {"shot_count": 4, "verified_receipt_count": 4, "human_labeled_count": 3, "paid_call_count": 4, "receipt_refs": ["receipts/"], "human_label_refs": ["labels.json"], "elapsed_seconds": 300, "observed_cost": None},
        }
        with self.assertRaisesRegex(ValueError, "story_proof"):
            runtime_acceptance.record_case(matrix, "paid-4", record)
        record["story_proof"]["human_labeled_count"] = 4
        updated = runtime_acceptance.record_case(matrix, "paid-4", record)
        self.assertEqual(updated["cases"][0]["status"], "PASS")
        self.assertEqual(matrix["cases"][0]["status"], "NOT_RUN")
        self.assertEqual(schema_lite.validate(updated, json.loads((ROOT / "schemas/runtime_acceptance_matrix.schema.json").read_text())), [])

    def test_cli_initializes_matrix_without_claiming_a_live_run(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "matrix.json"
            code, _output = image_factory_cli.run_cli(["acceptance-init", "--plugin-version", "0.8.0", "--out", str(target), "--json"])
            self.assertEqual(code, 0)
            self.assertTrue(all(case["status"] == "NOT_RUN" for case in json.loads(target.read_text())["cases"]))
            code, _output = image_factory_cli.run_cli(["acceptance-init", "--plugin-version", "0.8.0", "--out", str(target), "--json"])
            self.assertNotEqual(code, 0)

    def test_calibrate_cli_keeps_insufficient_strata_unadoptable(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            scores = base / "scores.json"
            context = base / "context.json"
            output = base / "calibration.json"
            scores.write_text(json.dumps({"schema_version": "1.4.0", "batch_id": "quality-study", "round": 1, "pass_threshold": 0.8, "advisory": {"enabled": True, "items": [{"item_id": "frame-01", "score": 0.9, "reason": ""}]}, "human_labels": [{"item_id": "frame-01", "label": "rejected"}], "reviewer_reports": [], "deterministic_gates": {"all_passed": True, "per_item": [{"item_id": "frame-01", "passed": True, "failures": []}]}, "decision": "fail"}))
            context.write_text(json.dumps({"frame-01": {"model": "model-a"}}))
            code, _ = image_factory_cli.run_cli(["calibrate", "--scores", str(scores), "--item-context", str(context), "--out", str(output), "--json"])
            self.assertEqual(code, 0)
            report = json.loads(output.read_text())
            self.assertEqual(report["threshold_candidates"], [])
            self.assertFalse(report["strata"][0]["sample_sufficient"])


if __name__ == "__main__":
    unittest.main()
