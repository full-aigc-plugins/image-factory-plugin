import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import optimizer  # noqa: E402
import schema_lite  # noqa: E402


BATCH_SCHEMA = json.loads((ROOT / "schemas/image_batch.schema.json").read_text(encoding="utf-8"))


def plan(items, round_number: int = 1, **overrides) -> dict:
    document = {
        "schema_version": "1.0.0",
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
        "items": items,
    }
    document.update(overrides)
    return document


def item(item_id: str, prompt: str = "a calm portrait") -> dict:
    return {"id": item_id, "prompt": prompt}


def scores(gates: dict, advisory: dict | None = None, labels: dict | None = None) -> dict:
    per_item = [
        {"item_id": item_id, "passed": passed, "failures": [] if passed else ["not_a_png"]}
        for item_id, passed in gates.items()
    ]
    return {
        "schema_version": "1.1.0",
        "batch_id": "portrait-study",
        "round": 1,
        "pass_threshold": 0.8,
        "deterministic_gates": {"all_passed": all(gates.values()), "per_item": per_item},
        "advisory": {
            "enabled": True,
            "items": [
                {"item_id": item_id, "score": score, "reason": "recorded"}
                for item_id, score in (advisory or {}).items()
            ],
        },
        "human_labels": [
            {"item_id": item_id, "label": label, "at": None}
            for item_id, label in (labels or {}).items()
        ],
        "decision": "pass" if all(gates.values()) else "fail",
    }


class NextRoundTests(unittest.TestCase):
    def optimize(self, current, evaluation, **overrides):
        kwargs = {
            "current_plan": current,
            "evaluation": evaluation,
            "rewrites": {},
            "retry_unchanged": set(),
        }
        kwargs.update(overrides)
        return optimizer.plan_next_round(**kwargs)

    def test_everything_passing_completes_the_job(self) -> None:
        current = plan([item("item-01"), item("item-02", "b")])
        result = self.optimize(current, scores({"item-01": True, "item-02": True}))
        self.assertTrue(result.complete)
        self.assertIsNone(result.next_plan)
        self.assertEqual(result.errors, ())

    def test_a_failed_item_becomes_a_new_round(self) -> None:
        current = plan([item("item-01"), item("item-02", "b")])
        result = self.optimize(
            current,
            scores({"item-01": False, "item-02": True}),
            rewrites={"item-01": "a calmer portrait with softer light"},
        )
        self.assertFalse(result.complete)
        self.assertEqual(result.next_plan["round"], 2)
        self.assertEqual([row["id"] for row in result.next_plan["items"]], ["item-01"])
        self.assertEqual(result.next_plan["items"][0]["prompt"], "a calmer portrait with softer light")

    def test_carried_forward_items_are_not_regenerated(self) -> None:
        """Re-running an item that already passed would spend the allowance for nothing."""
        current = plan([item("item-01"), item("item-02", "b"), item("item-03", "c")])
        result = self.optimize(
            current,
            scores({"item-01": True, "item-02": False, "item-03": True}),
            rewrites={"item-02": "better b"},
        )
        self.assertEqual(result.carried_forward, ("item-01", "item-03"))
        self.assertEqual(result.rework, ("item-02",))

    def test_the_next_round_conforms_to_the_batch_schema(self) -> None:
        current = plan([item("item-01")])
        result = self.optimize(
            current, scores({"item-01": False}), rewrites={"item-01": "try again"}
        )
        self.assertEqual(result.next_plan["schema_version"], "1.6.0")
        self.assertIs(result.next_plan["limits"]["require_approval_before_run"], True)
        self.assertIs(result.next_plan["judge_policy"]["require_human_labels"], True)
        self.assertEqual(schema_lite.validate(result.next_plan, BATCH_SCHEMA), [])

    def test_the_original_plan_is_never_mutated(self) -> None:
        current = plan([item("item-01")])
        snapshot = copy.deepcopy(current)
        self.optimize(current, scores({"item-01": False}), rewrites={"item-01": "changed"})
        self.assertEqual(current, snapshot)

    def test_limits_and_policy_are_preserved(self) -> None:
        current = plan([item("item-01")])
        result = self.optimize(current, scores({"item-01": False}), rewrites={"item-01": "x"})
        expected_limits = {**current["limits"], "require_approval_before_run": True}
        expected_policy = {**current["judge_policy"], "require_human_labels": True}
        self.assertEqual(result.next_plan["limits"], expected_limits)
        self.assertEqual(result.next_plan["judge_policy"], expected_policy)
        self.assertEqual(result.next_plan["goal"], current["goal"])

    def test_item_ids_are_preserved_so_history_lines_up(self) -> None:
        current = plan([item("item-01", "a"), item("item-02", "b")])
        result = self.optimize(
            current,
            scores({"item-01": False, "item-02": False}),
            rewrites={"item-01": "a2", "item-02": "b2"},
        )
        self.assertEqual({row["id"] for row in result.next_plan["items"]}, {"item-01", "item-02"})

    def test_a_new_round_is_genuinely_new_work(self) -> None:
        import plan_validator

        current = plan([item("item-01", "a")])
        result = self.optimize(
            current, scores({"item-01": False}), rewrites={"item-01": "a changed"}
        )
        first = plan_validator.validate_plan(plan([item("item-01", "a")]), base_dir=ROOT)
        second = plan_validator.validate_plan(result.next_plan, base_dir=ROOT)
        self.assertNotEqual(first.items[0].idempotency_key, second.items[0].idempotency_key)


class RewriteContractTests(unittest.TestCase):
    def optimize(self, current, evaluation, **overrides):
        kwargs = {
            "current_plan": current,
            "evaluation": evaluation,
            "rewrites": {},
            "retry_unchanged": set(),
        }
        kwargs.update(overrides)
        return optimizer.plan_next_round(**kwargs)

    def test_a_needs_work_item_without_an_instruction_is_an_error(self) -> None:
        current = plan([item("item-01")])
        result = self.optimize(current, scores({"item-01": False}))
        self.assertEqual([error.code for error in result.errors], ["optimizer_missing_instruction"])
        self.assertIsNone(result.next_plan)

    def test_retrying_unchanged_is_explicit(self) -> None:
        current = plan([item("item-01")])
        result = self.optimize(
            current, scores({"item-01": False}), retry_unchanged={"item-01"}
        )
        self.assertIsNone(result.errors[0] if result.errors else None)
        self.assertEqual(result.next_plan["items"][0]["prompt"], "a calm portrait")

    def test_a_rewrite_and_a_retry_unchanged_together_is_ambiguous(self) -> None:
        current = plan([item("item-01")])
        result = self.optimize(
            current,
            scores({"item-01": False}),
            rewrites={"item-01": "x"},
            retry_unchanged={"item-01"},
        )
        self.assertEqual([error.code for error in result.errors], ["optimizer_ambiguous_instruction"])

    def test_an_empty_rewrite_is_rejected(self) -> None:
        current = plan([item("item-01")])
        result = self.optimize(current, scores({"item-01": False}), rewrites={"item-01": "   "})
        self.assertEqual([error.code for error in result.errors], ["optimizer_empty_rewrite"])

    def test_instructions_for_items_that_already_passed_are_rejected(self) -> None:
        current = plan([item("item-01")])
        result = self.optimize(
            current, scores({"item-01": True}), rewrites={"item-01": "unnecessary"}
        )
        self.assertEqual([error.code for error in result.errors], ["optimizer_unexpected_instruction"])

    def test_an_instruction_for_an_unknown_item_is_rejected(self) -> None:
        current = plan([item("item-01")])
        result = self.optimize(
            current, scores({"item-01": False}), rewrites={"item-99": "who?"}
        )
        self.assertEqual([error.code for error in result.errors], ["optimizer_unknown_item"])


class ReworkSignalTests(unittest.TestCase):
    def optimize(self, current, evaluation, **overrides):
        kwargs = {
            "current_plan": current,
            "evaluation": evaluation,
            "rewrites": {},
            "retry_unchanged": set(),
        }
        kwargs.update(overrides)
        return optimizer.plan_next_round(**kwargs)

    def test_a_human_rejection_requires_rework_even_when_gates_passed(self) -> None:
        current = plan([item("item-01")])
        result = self.optimize(
            current,
            scores({"item-01": True}, labels={"item-01": "rejected"}),
            rewrites={"item-01": "closer to the reference"},
        )
        self.assertEqual(result.rework, ("item-01",))

    def test_a_low_advisory_score_requires_rework_when_advisory_is_enabled(self) -> None:
        current = plan([item("item-01")])
        evaluation = scores({"item-01": True}, advisory={"item-01": 0.3})
        result = self.optimize(current, evaluation, rewrites={"item-01": "more like the reference"})
        self.assertEqual(result.rework, ("item-01",))

    def test_a_low_advisory_score_is_ignored_when_advisory_is_disabled(self) -> None:
        current = plan([item("item-01")])
        current["judge_policy"]["advisory_enabled"] = False
        evaluation = scores({"item-01": True}, advisory={"item-01": 0.1})
        result = self.optimize(current, evaluation)
        self.assertTrue(result.complete)

    def test_an_approved_item_is_carried_forward(self) -> None:
        current = plan([item("item-01")])
        result = self.optimize(
            current, scores({"item-01": True}, labels={"item-01": "approved"})
        )
        self.assertTrue(result.complete)


class RoundCeilingTests(unittest.TestCase):
    def optimize(self, current, evaluation, **overrides):
        kwargs = {
            "current_plan": current,
            "evaluation": evaluation,
            "rewrites": {},
            "retry_unchanged": set(),
        }
        kwargs.update(overrides)
        return optimizer.plan_next_round(**kwargs)

    def test_the_round_cap_stops_optimization(self) -> None:
        current = plan([item("item-01")], round_number=3)
        result = self.optimize(
            current, scores({"item-01": False}), rewrites={"item-01": "one more try"}
        )
        self.assertEqual([error.code for error in result.errors], ["optimizer_round_cap_reached"])
        self.assertIsNone(result.next_plan)
        self.assertEqual(result.blocked, ("item-01",))

    def test_reaching_the_cap_is_reported_as_incomplete_not_as_success(self) -> None:
        current = plan([item("item-01")], round_number=3)
        result = self.optimize(current, scores({"item-01": False}), rewrites={"item-01": "x"})
        self.assertFalse(result.complete)
        self.assertIsNone(result.next_plan)


if __name__ == "__main__":
    unittest.main()
