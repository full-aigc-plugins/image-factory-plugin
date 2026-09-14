import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import contract_migrations  # noqa: E402


def canonical(document: object) -> str:
    return json.dumps(document, sort_keys=True, separators=(",", ":"))


def legacy_plan(**overrides) -> dict:
    plan = {
        "schema_version": "1.0.0",
        "batch_id": "portrait-study",
        "round": 1,
        "items": [{"id": "item-01", "prompt": "a calm portrait"}],
    }
    plan.update(overrides)
    return plan


def legacy_job(**overrides) -> dict:
    job = {
        "schema_version": "1.0.0",
        "job_id": "portrait-study",
        "state": "Completed",
        "revision": 7,
        "created_at": "2026-09-12T00:00:00Z",
        "updated_at": "2026-09-12T00:10:00Z",
        "batch": {"batch_id": "portrait-study"},
        "rounds": [1],
        "items": [{"item_id": "item-01", "state": "Generated", "attempts": 1}],
        "approval": None,
        "usage_limit": None,
        "error_category": None,
        "history": [],
    }
    job.update(overrides)
    return job


class ImageBatchMigrationTests(unittest.TestCase):
    def test_legacy_plan_is_upgraded_and_tightened(self) -> None:
        result = contract_migrations.migrate_image_batch(legacy_plan())
        self.assertEqual(result.document["schema_version"], "1.1.0")
        self.assertIs(result.document["limits"]["require_approval_before_run"], True)
        self.assertIs(result.document["judge_policy"]["require_human_labels"], True)
        self.assertEqual(len(result.notes), 1)

    def test_a_legacy_plan_cannot_keep_approval_optional(self) -> None:
        """The migration may tighten a plan, never preserve a weaker posture."""
        plan = legacy_plan(
            limits={"max_images": 5, "max_rounds": 2, "require_approval_before_run": False}
        )
        result = contract_migrations.migrate_image_batch(plan)
        self.assertIs(result.document["limits"]["require_approval_before_run"], True)

    def test_missing_sections_are_filled_with_safe_defaults(self) -> None:
        result = contract_migrations.migrate_image_batch(legacy_plan())
        self.assertEqual(result.document["limits"]["max_images"], 20)
        self.assertEqual(result.document["limits"]["max_rounds"], 3)
        self.assertEqual(result.document["judge_policy"]["min_dimension"], 256)

    def test_current_version_passes_through_unchanged(self) -> None:
        plan = legacy_plan(schema_version="1.1.0")
        plan["limits"] = {"max_images": 3, "max_rounds": 1, "require_approval_before_run": True}
        plan["judge_policy"] = {
            "min_dimension": 64,
            "reject_duplicates": True,
            "pass_threshold": 0.5,
            "require_human_labels": True,
        }
        result = contract_migrations.migrate_image_batch(plan)
        self.assertEqual(result.notes, ())
        self.assertEqual(result.document, plan)

    def test_non_object_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            contract_migrations.migrate_image_batch(["not", "an", "object"])

    def test_unsupported_version_is_rejected(self) -> None:
        for version in (None, 2, "2.0.0"):
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    contract_migrations.migrate_image_batch(legacy_plan(schema_version=version))

    def test_caller_dictionary_is_never_mutated(self) -> None:
        plan = legacy_plan()
        snapshot = canonical(plan)
        contract_migrations.migrate_image_batch(plan)
        self.assertEqual(canonical(plan), snapshot)


class FactoryJobMigrationTests(unittest.TestCase):
    def test_legacy_job_is_upgraded_with_transaction_fields(self) -> None:
        result = contract_migrations.migrate_factory_job(legacy_job())
        job = result.document
        self.assertEqual(job["schema_version"], "1.1.0")
        self.assertEqual(job["approval"], {"current": None, "history": []})
        self.assertIsNone(job["evaluation"])
        self.assertIsNone(job["optimization"])
        self.assertIn("attempt_id", job["items"][0])
        self.assertIsNone(job["items"][0]["attempt_id"])
        self.assertIn("attempt_started_at", job["items"][0])
        self.assertEqual(len(result.notes), 1)

    def test_observed_item_outcomes_and_history_are_preserved(self) -> None:
        result = contract_migrations.migrate_factory_job(legacy_job())
        item = result.document["items"][0]
        self.assertEqual(item["state"], "Generated")
        self.assertEqual(item["attempts"], 1)

    def test_job_carrying_approval_evidence_is_refused(self) -> None:
        """A 1.0.0 approval has no plan hash, so binding it would be a fiction."""
        job = legacy_job(approval={"approved": True})
        with self.assertRaises(ValueError):
            contract_migrations.migrate_factory_job(job)

    def test_non_object_batch_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            contract_migrations.migrate_factory_job(legacy_job(batch="portrait-study"))

    def test_null_batch_is_accepted(self) -> None:
        result = contract_migrations.migrate_factory_job(legacy_job(batch=None))
        self.assertIsNone(result.document["batch"])

    def test_current_version_passes_through_unchanged(self) -> None:
        job = legacy_job(
            schema_version="1.1.0",
            approval={"current": None, "history": []},
            evaluation=None,
            optimization=None,
        )
        job["items"][0]["attempt_id"] = None
        job["items"][0]["attempt_started_at"] = None
        result = contract_migrations.migrate_factory_job(job)
        self.assertEqual(result.notes, ())
        self.assertEqual(result.document, job)

    def test_non_object_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            contract_migrations.migrate_factory_job("not an object")

    def test_unsupported_version_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            contract_migrations.migrate_factory_job(legacy_job(schema_version="3.0.0"))

    def test_caller_dictionary_is_never_mutated(self) -> None:
        job = legacy_job()
        snapshot = canonical(job)
        contract_migrations.migrate_factory_job(job)
        self.assertEqual(canonical(job), snapshot)

    def test_items_without_attempt_fields_gain_them(self) -> None:
        job = legacy_job(items=[{"item_id": "item-01", "state": "Failed", "attempts": 2}])
        result = contract_migrations.migrate_factory_job(job)
        self.assertEqual(result.document["items"][0]["attempt_id"], None)
        self.assertEqual(result.document["items"][0]["attempt_started_at"], None)


if __name__ == "__main__":
    unittest.main()
