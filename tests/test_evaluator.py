import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import artifact_collector as collector  # noqa: E402
import evaluator  # noqa: E402
import plan_validator  # noqa: E402
import schema_lite  # noqa: E402


SCORES_SCHEMA = json.loads((ROOT / "schemas/scores.schema.json").read_text(encoding="utf-8"))
REAL_PNG = ROOT / "assets" / "logo.png"
SMALL_PNG = ROOT / "assets" / "composer-icon.png"


def make_item(item_id: str, prompt: str = "a calm portrait") -> plan_validator.PlanItem:
    return plan_validator.PlanItem(
        id=item_id,
        prompt=prompt,
        round=1,
        reference_images=(),
        reference_sha256=(),
        idempotency_key=plan_validator.compute_idempotency_key(
            batch_id="portrait-study",
            item_id=item_id,
            round_number=1,
            prompt=prompt,
            reference_sha256=(),
        ),
    )


class EvaluationFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.generation_dir = self.base / "generated_images"
        self.destination = self.base / "batch-out"
        self.generation_dir.mkdir()
        self.destination.mkdir()
        self._counter = 0

    def collect(self, item: plan_validator.PlanItem, source: Path = REAL_PNG) -> dict:
        self._counter += 1
        before = collector.snapshot(self.generation_dir)
        call_id = f"call-{self._counter}"
        target = self.generation_dir / "session-a" / f"{call_id}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        result = collector.collect_artifact(
            item=item,
            batch_id="portrait-study",
            generation_dir=self.generation_dir,
            destination_dir=self.destination,
            before=before,
            min_dimension=64,
        )
        assert result.ok, result.failure
        return result.receipt

    def evaluate(self, items, receipts, **overrides):
        kwargs = {
            "batch_id": "portrait-study",
            "round_number": 1,
            "items": tuple(items),
            "receipts": receipts,
            "destination_dir": self.destination,
            "min_dimension": 64,
            "reject_duplicates": True,
            "pass_threshold": 0.8,
            "advisory_enabled": False,
            "require_human_labels": False,
        }
        kwargs.update(overrides)
        return evaluator.evaluate_batch(**kwargs)

    def cleanup(self) -> None:
        self._tmp.cleanup()


class DeterministicGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = EvaluationFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_clean_batch_passes(self) -> None:
        item = make_item("item-01")
        receipt = self.fixture.collect(item)
        result = self.fixture.evaluate([item], {"item-01": receipt})
        self.assertTrue(result.ok, result.scores)
        self.assertTrue(result.scores["deterministic_gates"]["all_passed"])
        self.assertEqual(result.scores["decision"], "pass")
        self.assertEqual(result.scores["deterministic_gates"]["per_item"][0]["failures"], [])

    def test_missing_receipt_fails_the_item(self) -> None:
        item = make_item("item-01")
        result = self.fixture.evaluate([item], {})
        self.assertFalse(result.ok)
        self.assertEqual(result.scores["decision"], "fail")
        self.assertIn("missing_artifact", result.scores["deterministic_gates"]["per_item"][0]["failures"])

    def test_deleted_artifact_is_reported_as_missing(self) -> None:
        item = make_item("item-01")
        receipt = self.fixture.collect(item)
        (self.fixture.destination / receipt["path"]).unlink()
        result = self.fixture.evaluate([item], {"item-01": receipt})
        self.assertIn("missing_artifact", result.scores["deterministic_gates"]["per_item"][0]["failures"])

    def test_tampered_artifact_is_reported_as_a_hash_mismatch(self) -> None:
        item = make_item("item-01")
        receipt = self.fixture.collect(item)
        target = self.fixture.destination / receipt["path"]
        target.write_bytes(target.read_bytes() + b"tampered")
        result = self.fixture.evaluate([item], {"item-01": receipt})
        self.assertIn("hash_mismatch", result.scores["deterministic_gates"]["per_item"][0]["failures"])

    def test_small_artifact_fails_the_dimension_gate(self) -> None:
        item = make_item("item-01")
        receipt = self.fixture.collect(item, source=SMALL_PNG)
        result = self.fixture.evaluate([item], {"item-01": receipt}, min_dimension=512)
        self.assertIn("below_min_dimension", result.scores["deterministic_gates"]["per_item"][0]["failures"])

    def test_identical_content_across_items_is_flagged_for_every_participant(self) -> None:
        """Repeat content cannot be blamed on whichever item happened to come second."""
        first, second = make_item("item-01"), make_item("item-02", prompt="another portrait")
        receipts = {
            "item-01": self.fixture.collect(first),
            "item-02": self.fixture.collect(second),
        }
        result = self.fixture.evaluate([first, second], receipts)
        gates = {row["item_id"]: row for row in result.scores["deterministic_gates"]["per_item"]}
        self.assertIn("duplicate_content", gates["item-01"]["failures"])
        self.assertIn("duplicate_content", gates["item-02"]["failures"])

    def test_duplicate_detection_is_order_deterministic(self) -> None:
        first, second = make_item("item-01"), make_item("item-02", prompt="another")
        receipts = {
            "item-01": self.fixture.collect(first),
            "item-02": self.fixture.collect(second),
        }
        forward = self.fixture.evaluate([first, second], receipts)
        reverse = self.fixture.evaluate([second, first], receipts)
        forward_gates = {row["item_id"]: row["failures"] for row in forward.scores["deterministic_gates"]["per_item"]}
        reverse_gates = {row["item_id"]: row["failures"] for row in reverse.scores["deterministic_gates"]["per_item"]}
        self.assertEqual(forward_gates, reverse_gates)

    def test_duplicates_are_tolerated_when_the_policy_allows_them(self) -> None:
        first, second = make_item("item-01"), make_item("item-02", prompt="another")
        receipts = {
            "item-01": self.fixture.collect(first),
            "item-02": self.fixture.collect(second),
        }
        result = self.fixture.evaluate([first, second], receipts, reject_duplicates=False)
        self.assertTrue(result.ok, result.scores)

    def test_a_failing_item_makes_the_batch_fail(self) -> None:
        good, bad = make_item("item-01"), make_item("item-02", prompt="another")
        receipts = {"item-01": self.fixture.collect(good), "item-02": self.fixture.collect(bad, source=SMALL_PNG)}
        result = self.fixture.evaluate([good, bad], receipts, min_dimension=512)
        self.assertFalse(result.ok)
        self.assertFalse(result.scores["deterministic_gates"]["all_passed"])
        self.assertEqual(result.scores["decision"], "fail")


class AdvisoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = EvaluationFixture()
        self.addCleanup(self.fixture.cleanup)
        self.item = make_item("item-01")
        self.receipt = self.fixture.collect(self.item)
        self.receipts = {"item-01": self.receipt}

    def test_advisory_scores_are_recorded_but_do_not_fail_the_batch(self) -> None:
        result = self.fixture.evaluate(
            [self.item],
            self.receipts,
            advisory={"item-01": (0.1, "looks wrong to me")},
            advisory_enabled=False,
        )
        self.assertTrue(result.ok, result.scores)
        self.assertEqual(result.scores["decision"], "pass")
        self.assertFalse(result.scores["advisory"]["enabled"])
        self.assertEqual(result.scores["advisory"]["items"][0]["score"], 0.1)

    def test_low_advisory_score_requests_a_human_when_advisory_is_enabled(self) -> None:
        result = self.fixture.evaluate(
            [self.item],
            self.receipts,
            advisory={"item-01": (0.4, "style does not match")},
            advisory_enabled=True,
        )
        self.assertEqual(result.scores["decision"], "pending_approval")
        self.assertTrue(result.ok, "a low advisory score is not a deterministic failure")

    def test_high_advisory_score_passes(self) -> None:
        result = self.fixture.evaluate(
            [self.item],
            self.receipts,
            advisory={"item-01": (0.95, "matches the reference")},
            advisory_enabled=True,
        )
        self.assertEqual(result.scores["decision"], "pass")

    def test_advisory_score_outside_the_unit_interval_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.fixture.evaluate(
                [self.item],
                self.receipts,
                advisory={"item-01": (1.4, "too high")},
                advisory_enabled=True,
            )

    def test_advisory_for_an_unknown_item_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.fixture.evaluate(
                [self.item],
                self.receipts,
                advisory={"item-99": (0.9, "who?")},
                advisory_enabled=True,
            )


class HumanLabelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = EvaluationFixture()
        self.addCleanup(self.fixture.cleanup)
        self.item = make_item("item-01")
        self.receipts = {"item-01": self.fixture.collect(self.item)}

    def test_a_human_rejection_outranks_a_perfect_advisory_score(self) -> None:
        result = self.fixture.evaluate(
            [self.item],
            self.receipts,
            advisory={"item-01": (1.0, "flawless")},
            advisory_enabled=True,
            human_labels={"item-01": "rejected"},
        )
        self.assertEqual(result.scores["decision"], "fail")
        self.assertFalse(result.ok)

    def test_required_labels_leave_the_decision_pending(self) -> None:
        result = self.fixture.evaluate(
            [self.item], self.receipts, require_human_labels=True
        )
        self.assertEqual(result.scores["decision"], "pending_approval")

    def test_required_labels_are_satisfied_once_provided(self) -> None:
        result = self.fixture.evaluate(
            [self.item],
            self.receipts,
            require_human_labels=True,
            human_labels={"item-01": "approved"},
        )
        self.assertEqual(result.scores["decision"], "pass")

    def test_default_label_is_unlabeled(self) -> None:
        result = self.fixture.evaluate([self.item], self.receipts)
        self.assertEqual(result.scores["human_labels"][0]["label"], "unlabeled")

    def test_unknown_label_value_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.fixture.evaluate([self.item], self.receipts, human_labels={"item-01": "maybe"})


class ScoresDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = EvaluationFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_scores_document_conforms_to_the_published_schema(self) -> None:
        item = make_item("item-01")
        receipt = self.fixture.collect(item)
        result = self.fixture.evaluate(
            [item],
            {"item-01": receipt},
            advisory={"item-01": (0.9, "close enough")},
            advisory_enabled=True,
            human_labels={"item-01": "approved"},
        )
        self.assertEqual(schema_lite.validate(result.scores, SCORES_SCHEMA), [])

    def test_scores_document_is_json_serialisable(self) -> None:
        item = make_item("item-01")
        receipt = self.fixture.collect(item)
        result = self.fixture.evaluate([item], {"item-01": receipt})
        self.assertEqual(json.loads(json.dumps(result.scores))["batch_id"], "portrait-study")

    def test_pass_threshold_is_echoed(self) -> None:
        item = make_item("item-01")
        receipt = self.fixture.collect(item)
        result = self.fixture.evaluate([item], {"item-01": receipt}, pass_threshold=0.55)
        self.assertEqual(result.scores["pass_threshold"], 0.55)

    def test_every_failing_item_is_listed(self) -> None:
        items = [make_item("item-01"), make_item("item-02", prompt="b"), make_item("item-03", prompt="c")]
        result = self.fixture.evaluate(items, {"item-02": self.fixture.collect(items[1])})
        gates = {row["item_id"]: row["passed"] for row in result.scores["deterministic_gates"]["per_item"]}
        self.assertEqual(len(gates), 3)
        self.assertFalse(gates["item-01"])
        self.assertTrue(gates["item-02"])
        self.assertFalse(gates["item-03"])


if __name__ == "__main__":
    unittest.main()
