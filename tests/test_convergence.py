import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import atomic_json
import evaluator
import job_ledger
import optimizer
import schema_lite

SCORES_SCHEMA = json.loads((ROOT / "schemas/scores.schema.json").read_text(encoding="utf-8"))


def history_entry(round_number: int, best: float | None, dims=(), decision: str = "fail") -> dict:
    return {
        "round": round_number,
        "decision": decision,
        "advisory_enabled": best is not None,
        "scored_items": 2 if best is not None else 0,
        "best_score": best,
        "mean_score": best,
        "gap_dimensions": list(dims),
    }


def plan(items, round_number: int = 1):
    return {
        "schema_version": "1.1.0",
        "batch_id": "portrait-study",
        "round": round_number,
        "goal": "match the reference lighting",
        "limits": {"max_images": 20, "max_rounds": 3, "require_approval_before_run": True},
        "judge_policy": {
            "min_dimension": 64,
            "reject_duplicates": True,
            "pass_threshold": 0.8,
            "advisory_enabled": True,
        },
        "items": [{"id": item_id, "prompt": "a calm portrait"} for item_id in items],
    }


def evaluation(advisory_items, gates=None, labels=None, round_number: int = 1):
    gates = gates if gates is not None else {"item-01": True}
    per_item = [
        {"item_id": item_id, "passed": passed, "failures": [] if passed else ["not_a_png"]}
        for item_id, passed in gates.items()
    ]
    return {
        "schema_version": "1.1.0",
        "batch_id": "portrait-study",
        "round": round_number,
        "pass_threshold": 0.8,
        "deterministic_gates": {"all_passed": all(gates.values()), "per_item": per_item},
        "advisory": {"enabled": True, "items": advisory_items},
        "human_labels": [
            {"item_id": item_id, "label": label, "at": None}
            for item_id, label in (labels or {}).items()
        ],
        "decision": "pass" if all(gates.values()) else "fail",
    }


class DimensionedCritiqueTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_dimension_below_threshold_drives_rework_and_the_instruction_gate_holds(self) -> None:
        """A dimension gap may mark rework, but it still cannot open a round."""
        rows = [
            {
                "item_id": "item-01",
                "score": 0.9,
                "reason": "total above threshold",
                "dimensions": [
                    {"name": "materials", "score": 0.5, "evidence": "amber mark, not emerald", "complete": True},
                ],
            }
        ]
        outcome = optimizer.plan_next_round(
            current_plan=plan(["item-01"]),
            evaluation=evaluation(rows),
            rewrites={},
            retry_unchanged=set(),
        )
        self.assertEqual(outcome.rework, ("item-01",))
        self.assertFalse(outcome.complete)
        codes = [error.code for error in outcome.errors]
        self.assertIn(optimizer.NEEDS_WORK_WITHOUT_INSTRUCTION, codes)

    def test_incomplete_dimension_is_reported_but_never_a_gap(self) -> None:
        rows = [
            {
                "item_id": "item-01",
                "score": 0.9,
                "reason": "total above threshold",
                "dimensions": [
                    {"name": "materials", "score": 0.5, "complete": False},
                ],
            }
        ]
        outcome = optimizer.plan_next_round(
            current_plan=plan(["item-01"]),
            evaluation=evaluation(rows),
            rewrites={},
            retry_unchanged=set(),
        )
        self.assertTrue(outcome.complete)
        self.assertEqual(outcome.rework, ())

    def test_evaluator_records_dimension_completeness_and_conforms(self) -> None:
        class Item:
            id = "item-01"

        result = evaluator.evaluate_batch(
            batch_id="portrait-study",
            round_number=1,
            items=[Item()],
            receipts={},
            destination_dir=self._tmp.name,
            min_dimension=16,
            reject_duplicates=False,
            pass_threshold=0.8,
            advisory_enabled=True,
            require_human_labels=False,
            advisory={
                "item-01": {
                    "score": 0.75,
                    "reason": "recorded",
                    "dimensions": [
                        {"name": "composition", "score": 0.9, "evidence": "declared margin present"},
                        {"name": "materials", "score": 0.5},
                    ],
                }
            },
        )
        rows = result.scores["advisory"]["items"]
        dimensions = {row["name"]: row for row in rows[0]["dimensions"]}
        self.assertTrue(dimensions["composition"]["complete"])
        self.assertFalse(dimensions["materials"]["complete"])
        self.assertEqual(
            schema_lite.validate(result.scores, SCORES_SCHEMA),
            [],
            "the recorded scores document must conform to the published schema",
        )

    def test_evaluator_rejects_malformed_dimensions(self) -> None:
        class Item:
            id = "item-01"

        base = {
            "batch_id": "portrait-study",
            "round_number": 1,
            "items": [Item()],
            "receipts": {},
            "destination_dir": self._tmp.name,
            "min_dimension": 16,
            "reject_duplicates": False,
            "pass_threshold": 0.8,
            "advisory_enabled": True,
            "require_human_labels": False,
        }
        bad_advisories = [
            {"item-01": {"score": 0.5, "dimensions": [{"name": "m", "score": 1.5, "evidence": "x"}]}},
            {"item-01": {"score": 0.5, "dimensions": [{"name": "", "score": 0.5, "evidence": "x"}]}},
            {"item-01": {"score": 0.5, "dimensions": [{"name": "m", "score": 0.5, "scale": 2}]}},
            {"item-01": {"score": 0.5, "dimensions": "materials"}},
        ]
        for advisory in bad_advisories:
            with self.subTest(advisory=advisory), self.assertRaises(ValueError):
                evaluator.evaluate_batch(advisory=advisory, **base)

    def test_summarize_numeric_reports_gaps_and_honest_absence(self) -> None:
        scores = {
            "advisory": {
                "enabled": True,
                "items": [
                    {
                        "item_id": "item-01",
                        "score": 0.82,
                        "reason": "r",
                        "dimensions": [
                            {"name": "materials", "score": 0.5, "evidence": "e", "complete": True},
                            {"name": "lighting", "score": 0.2, "complete": False},
                        ],
                    },
                    {"item_id": "item-02", "score": 0.9, "reason": "r"},
                ],
            }
        }
        summary = evaluator.summarize_numeric(scores, 0.8)
        self.assertEqual(summary["best_score"], 0.9)
        self.assertEqual(summary["mean_score"], 0.86)
        self.assertEqual(summary["gap_dimensions"], ["materials"])
        self.assertEqual(summary["scored_items"], 2)
        absent = evaluator.summarize_numeric({"advisory": {"enabled": False, "items": []}}, 0.8)
        self.assertIsNone(absent["best_score"])
        self.assertEqual(absent["scored_items"], 0)
        self.assertIs(absent["advisory_enabled"], False)


class LedgerNumericHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "job.json"
        atomic_json.write_json_atomic(self.path, job_ledger.new_job("portrait-study"))
        self.ledger = job_ledger.JobLedger(self.path, job_id="portrait-study")
        self.ledger.bind_plan(plan_sha256="a" * 64, round_number=1, image_count=2)
        payload = self.ledger.read()
        payload["state"] = "Completed"
        self.ledger.write(payload)

    def _advance_to_round(self, round_number: int) -> None:
        payload = self.ledger.read()
        payload["batch"]["round"] = round_number
        payload["state"] = "Completed"
        self.ledger.write(payload)

    def test_round_numbers_are_recorded_and_survive_a_scores_overwrite(self) -> None:
        self.ledger.record_evaluation_final(
            "b" * 64,
            "fail",
            numeric_summary={
                "advisory_enabled": True,
                "scored_items": 2,
                "best_score": 0.82,
                "mean_score": 0.7,
                "gap_dimensions": ["materials"],
            },
        )
        self._advance_to_round(2)
        self.ledger.record_evaluation_final(
            "c" * 64,
            "fail",
            numeric_summary={
                "advisory_enabled": True,
                "scored_items": 2,
                "best_score": 0.74,
                "mean_score": 0.7,
                "gap_dimensions": ["materials", "lighting"],
            },
        )
        # The caller overwrites the external scores document at its own path.
        (Path(self._tmp.name) / "scores.json").write_text("{}", encoding="utf-8")
        stored = job_ledger.load_ledger(self.path)
        history = stored["numeric_history"]
        self.assertEqual([row["round"] for row in history], [1, 2])
        best = max(history, key=lambda row: row["best_score"])
        self.assertEqual(best["round"], 1, "the best round must stay readable from the ledger")
        self.assertLess(history[-1]["best_score"], history[0]["best_score"])

    def test_reevaluating_one_round_replaces_its_row(self) -> None:
        self.ledger.record_evaluation_final(
            "b" * 64,
            "pending_approval",
            numeric_summary={
                "advisory_enabled": True,
                "scored_items": 2,
                "best_score": 0.6,
                "mean_score": 0.6,
                "gap_dimensions": [],
            },
        )
        payload = self.ledger.read()
        payload["state"] = "PendingApproval"
        self.ledger.write(payload)
        self.ledger.record_evaluation_final(
            "c" * 64,
            "pending_approval",
            numeric_summary={
                "advisory_enabled": True,
                "scored_items": 2,
                "best_score": 0.6,
                "mean_score": 0.6,
                "gap_dimensions": ["materials"],
            },
        )
        history = job_ledger.load_ledger(self.path)["numeric_history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["gap_dimensions"], ["materials"])

    def test_a_round_without_numbers_records_the_absence(self) -> None:
        payload = self.ledger.record_evaluation_final("d" * 64, "pass")
        entry = payload["numeric_history"][0]
        self.assertIsNone(entry["best_score"])
        self.assertEqual(entry["scored_items"], 0)
        self.assertIs(entry["advisory_enabled"], False)
        self.assertEqual(
            schema_lite.validate(payload, json.loads(
                (ROOT / "schemas/factory_job.schema.json").read_text(encoding="utf-8")
            )),
            [],
        )

    def test_a_malformed_summary_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.ledger.record_evaluation_final(
                "b" * 64,
                "fail",
                numeric_summary={"advisory_enabled": True, "best_score": 7.0},
            )


class ConvergenceSignalTests(unittest.TestCase):
    def test_a_drop_is_reported_as_regression_with_both_rounds(self) -> None:
        signals = optimizer.detect_convergence(
            [history_entry(1, 0.82), history_entry(2, 0.7)]
        )
        kinds = [signal.kind for signal in signals]
        self.assertEqual(kinds, ["regression"])
        evidence = " ".join(signals[0].evidence)
        self.assertIn("round 1", evidence)
        self.assertIn("round 2", evidence)

    def test_two_flat_rounds_report_an_approaching_stall(self) -> None:
        signals = optimizer.detect_convergence(
            [history_entry(1, 0.85), history_entry(2, 0.86), history_entry(3, 0.86)]
        )
        self.assertIn("stall_approaching", [signal.kind for signal in signals])

    def test_a_dimension_named_twice_in_a_row_reports_an_approaching_stall(self) -> None:
        signals = optimizer.detect_convergence(
            [
                history_entry(1, 0.5, ["materials"]),
                history_entry(2, 0.9, ["materials"]),
            ]
        )
        self.assertIn("stall_approaching", [signal.kind for signal in signals])

    def test_an_established_stall_subsumes_the_approaching_one(self) -> None:
        signals = optimizer.detect_convergence(
            [
                history_entry(1, 0.85),
                history_entry(2, 0.86),
                history_entry(3, 0.86),
                history_entry(4, 0.86),
            ]
        )
        kinds = [signal.kind for signal in signals]
        self.assertIn("stall_established", kinds)
        self.assertNotIn("stall_approaching", kinds)

    def test_improving_rounds_report_nothing(self) -> None:
        signals = optimizer.detect_convergence(
            [
                history_entry(1, 0.5),
                history_entry(2, 0.7),
                history_entry(3, 0.9),
            ]
        )
        self.assertEqual(signals, ())

    def test_rounds_without_numbers_are_excluded_and_stay_silent(self) -> None:
        self.assertEqual(optimizer.detect_convergence([]), ())
        signals = optimizer.detect_convergence(
            [history_entry(1, None), history_entry(2, None)]
        )
        self.assertEqual(signals, ())


class StallEnforcementTests(unittest.TestCase):
    def optimize(self, current, current_evaluation, history, **overrides):
        kwargs = {
            "current_plan": current,
            "evaluation": current_evaluation,
            "rewrites": {},
            "retry_unchanged": set(),
            "numeric_history": history,
        }
        kwargs.update(overrides)
        return optimizer.plan_next_round(**kwargs)

    def test_an_approaching_stall_rejects_retry_unchanged(self) -> None:
        history = [history_entry(1, 0.85), history_entry(2, 0.86), history_entry(3, 0.86)]
        outcome = self.optimize(
            plan(["item-01"]),
            evaluation([{"item_id": "item-01", "score": 0.5, "reason": "r"}]),
            history,
            retry_unchanged={"item-01"},
        )
        codes = [error.code for error in outcome.errors]
        self.assertIn(optimizer.STALL_REQUIRES_REWRITE, codes)
        self.assertFalse(outcome.complete)

    def test_an_approaching_stall_with_a_real_rewrite_proceeds_and_reports(self) -> None:
        history = [history_entry(1, 0.85), history_entry(2, 0.86), history_entry(3, 0.86)]
        outcome = self.optimize(
            plan(["item-01"]),
            evaluation([{"item_id": "item-01", "score": 0.5, "reason": "r"}]),
            history,
            rewrites={"item-01": "restructure the scene around a single key light"},
        )
        self.assertIsNotNone(outcome.next_plan)
        self.assertIn("stall_approaching", [signal.kind for signal in outcome.signals])

    def test_an_established_stall_stops_even_with_an_instruction(self) -> None:
        history = [
            history_entry(1, 0.85),
            history_entry(2, 0.86),
            history_entry(3, 0.86),
            history_entry(4, 0.86),
        ]
        outcome = self.optimize(
            plan(["item-01"]),
            evaluation([{"item_id": "item-01", "score": 0.5, "reason": "r"}]),
            history,
            rewrites={"item-01": "try another dramatic approach"},
        )
        self.assertIsNone(outcome.next_plan)
        codes = [error.code for error in outcome.errors]
        self.assertIn(optimizer.STALL_ESTABLISHED, codes)
        self.assertEqual(outcome.blocked, ("item-01",))
        self.assertIn("stall_established", [signal.kind for signal in outcome.signals])

    def test_no_history_means_no_signals_and_the_gate_still_holds(self) -> None:
        outcome = self.optimize(
            plan(["item-01"]),
            evaluation([{"item_id": "item-01", "score": 0.5, "reason": "r"}]),
            [],
        )
        self.assertEqual(outcome.signals, ())
        codes = [error.code for error in outcome.errors]
        self.assertEqual(codes, [optimizer.NEEDS_WORK_WITHOUT_INSTRUCTION])

    def test_the_round_cap_still_reports_incomplete_and_cap_only(self) -> None:
        history = [
            history_entry(1, 0.5),
            history_entry(2, 0.9),
            history_entry(3, 0.7),
        ]
        outcome = self.optimize(
            plan(["item-01"], round_number=3),
            evaluation([{"item_id": "item-01", "score": 0.5, "reason": "r"}], round_number=3),
            history,
            rewrites={"item-01": "another pass"},
        )
        codes = [error.code for error in outcome.errors]
        self.assertEqual(codes, [optimizer.ROUND_CAP_REACHED])
        self.assertIn("regression", [signal.kind for signal in outcome.signals])
        self.assertNotIn("stall_established", [signal.kind for signal in outcome.signals])
        self.assertIsNone(outcome.next_plan)


if __name__ == "__main__":
    unittest.main()
