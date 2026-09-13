import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import contract_migrations  # noqa: E402
import schema_lite  # noqa: E402


def load_schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


class ImageBatchMigrationTests(unittest.TestCase):
    def test_legacy_plan_is_safety_strengthened_without_mutating_input(self) -> None:
        original = {
            "schema_version": "1.0.0",
            "batch_id": "portrait-study",
            "round": 1,
            "limits": {
                "max_images": 6,
                "max_rounds": 3,
                "require_approval_before_run": False,
            },
            "judge_policy": {
                "min_dimension": 256,
                "reject_duplicates": True,
                "pass_threshold": 0.8,
                "require_human_labels": False,
            },
            "items": [{"id": "item-01", "prompt": "portrait"}],
        }
        before = json.dumps(original, sort_keys=True)

        result = contract_migrations.migrate_image_batch(original)

        self.assertEqual(result.document["schema_version"], "1.1.0")
        self.assertIs(result.document["limits"]["require_approval_before_run"], True)
        self.assertIs(result.document["judge_policy"]["require_human_labels"], True)
        self.assertEqual(result.notes, ("migrated image batch 1.0.0 to 1.1.0",))
        self.assertEqual(schema_lite.validate(result.document, load_schema("image_batch.schema.json")), [])
        self.assertEqual(json.dumps(original, sort_keys=True), before)

    def test_current_plan_returns_an_unchanged_copy(self) -> None:
        original = {
            "schema_version": "1.1.0",
            "batch_id": "portrait-study",
            "round": 1,
            "items": [{"id": "item-01", "prompt": "portrait"}],
        }
        result = contract_migrations.migrate_image_batch(original)
        self.assertEqual(result.document, original)
        self.assertIsNot(result.document, original)
        self.assertEqual(result.notes, ())

    def test_plan_rejects_non_objects_and_unsupported_versions(self) -> None:
        for document in ([], None, "plan"):
            with self.subTest(document=document), self.assertRaises(ValueError):
                contract_migrations.migrate_image_batch(document)
        for version in (None, 1, "2.0.0"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                contract_migrations.migrate_image_batch({"schema_version": version})


class FactoryJobMigrationTests(unittest.TestCase):
    def test_legacy_job_preserves_outcomes_and_history_without_inventing_approval(self) -> None:
        original = {
            "schema_version": "1.0.0",
            "job_id": "portrait-study",
            "state": "Completed",
            "revision": 4,
            "created_at": "2026-09-14T12:00:00Z",
            "updated_at": "2026-09-14T12:05:00Z",
            "batch": None,
            "rounds": [1],
            "items": [{
                "item_id": "item-01",
                "state": "Generated",
                "attempts": 1,
                "receipt_id": "receipt-01",
                "idempotency_key": "a" * 64,
                "error_category": None,
            }],
            "approval": None,
            "usage_limit": None,
            "error_category": None,
            "history": [{
                "from_state": "Running",
                "to_state": "Completed",
                "at": "2026-09-14T12:05:00Z",
            }],
        }
        before = copy.deepcopy(original)

        result = contract_migrations.migrate_factory_job(original)

        self.assertEqual(result.document["schema_version"], "1.1.0")
        self.assertEqual(result.document["approval"], {"current": None, "history": []})
        self.assertIsNone(result.document["evaluation"])
        self.assertIsNone(result.document["optimization"])
        self.assertEqual(result.document["items"][0]["state"], "Generated")
        self.assertIsNone(result.document["items"][0]["attempt_id"])
        self.assertEqual(result.document["history"], original["history"])
        self.assertEqual(schema_lite.validate(result.document, load_schema("factory_job.schema.json")), [])
        self.assertEqual(original, before)

    def test_current_job_returns_an_unchanged_copy(self) -> None:
        original = {"schema_version": "1.1.0", "nested": {"value": 1}}
        result = contract_migrations.migrate_factory_job(original)
        result.document["nested"]["value"] = 2
        self.assertEqual(original["nested"]["value"], 1)
        self.assertEqual(result.notes, ())

    def test_legacy_job_rejects_approval_evidence_it_cannot_prove(self) -> None:
        with self.assertRaisesRegex(ValueError, "approval evidence"):
            contract_migrations.migrate_factory_job({
                "schema_version": "1.0.0",
                "approval": {"approved": True},
            })

    def test_job_rejects_non_objects_and_unsupported_versions(self) -> None:
        for document in ([], None, "job"):
            with self.subTest(document=document), self.assertRaises(ValueError):
                contract_migrations.migrate_factory_job(document)
        for version in (None, 1, "2.0.0"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                contract_migrations.migrate_factory_job({"schema_version": version})


if __name__ == "__main__":
    unittest.main()
