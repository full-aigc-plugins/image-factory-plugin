import hashlib
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import plan_validator  # noqa: E402
import schema_lite  # noqa: E402


SCHEMA = json.loads((ROOT / "schemas/image_batch.schema.json").read_text(encoding="utf-8"))


def minimal_plan(**overrides) -> dict:
    plan = {
        "schema_version": "1.3.0",
        "batch_id": "portrait-study",
        "round": 1,
        "limits": {
            "max_images": 20,
            "max_rounds": 3,
            "require_approval_before_run": True,
        },
        "judge_policy": {
            "min_dimension": 256,
            "reject_duplicates": True,
            "pass_threshold": 0.8,
            "require_human_labels": True,
        },
        "items": [{"id": "item-01", "prompt": "A calm portrait on rice paper"}],
    }
    plan.update(overrides)
    return plan


def _valid_png(red: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(bytes((0, red, 0, 0)))
    return header + chunk(b"IHDR", ihdr) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


def valid_plan_1_1() -> dict:
    return minimal_plan()


def plan_with_reference(reference: Path) -> dict:
    return minimal_plan(
        items=[{"id": "item-01", "prompt": "p", "reference_images": [str(reference)]}]
    )


def second_png() -> bytes:
    return _valid_png(2)


def plan_a() -> dict:
    return minimal_plan()


def same_plan_with_different_key_order() -> dict:
    return {
        "items": [{"prompt": "A calm portrait on rice paper", "id": "item-01"}],
        "judge_policy": {
            "require_human_labels": True,
            "pass_threshold": 0.8,
            "reject_duplicates": True,
            "min_dimension": 256,
        },
        "limits": {
            "require_approval_before_run": True,
            "max_rounds": 3,
            "max_images": 20,
        },
        "round": 1,
        "batch_id": "portrait-study",
        "schema_version": "1.3.0",
    }


class PlanFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def reference(self, name: str, content: bytes = b"\x89PNG\r\n\x1a\nreference") -> Path:
        target = self.base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def validate(self, plan: dict) -> plan_validator.PlanResult:
        return plan_validator.validate_plan(plan, base_dir=self.base)

    def cleanup(self) -> None:
        self._tmp.cleanup()


class SchemaLiteTests(unittest.TestCase):
    def test_rejects_unknown_property(self) -> None:
        errors = schema_lite.validate({"extra": 1}, SCHEMA)
        self.assertTrue(any("extra" in error for error in errors), errors)

    def test_accepts_valid_instance(self) -> None:
        self.assertEqual(schema_lite.validate(minimal_plan(), SCHEMA), [])

    def test_enforces_pattern_and_bounds(self) -> None:
        errors = schema_lite.validate(minimal_plan(batch_id="X"), SCHEMA)
        self.assertTrue(any("batch_id" in error for error in errors), errors)
        errors = schema_lite.validate(minimal_plan(round=0), SCHEMA)
        self.assertTrue(any("round" in error for error in errors), errors)

    def test_resolves_local_refs(self) -> None:
        plan = minimal_plan(items=[{"id": "item-01", "prompt": ""}])
        errors = schema_lite.validate(plan, SCHEMA)
        self.assertTrue(any("minLength" in error or "prompt" in error for error in errors), errors)

    def test_enforces_reference_image_ceiling(self) -> None:
        item = {"id": "item-01", "prompt": "p", "reference_images": [f"r{n}.png" for n in range(6)]}
        errors = schema_lite.validate(minimal_plan(items=[item]), SCHEMA)
        self.assertTrue(any("maxItems" in error for error in errors), errors)


class PlanValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PlanFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_valid_plan_yields_idempotency_key(self) -> None:
        result = self.fixture.validate(minimal_plan())
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(result.items), 1)
        key = result.items[0].idempotency_key
        self.assertRegex(key, r"^[0-9a-f]{64}$")

    def test_idempotency_key_is_deterministic(self) -> None:
        first = self.fixture.validate(minimal_plan()).items[0].idempotency_key
        second = self.fixture.validate(minimal_plan()).items[0].idempotency_key
        self.assertEqual(first, second)

    def test_idempotency_key_changes_with_prompt_and_round(self) -> None:
        base = self.fixture.validate(minimal_plan()).items[0].idempotency_key
        changed_prompt = self.fixture.validate(
            minimal_plan(items=[{"id": "item-01", "prompt": "a different portrait"}])
        ).items[0].idempotency_key
        changed_round = self.fixture.validate(minimal_plan(round=2)).items[0].idempotency_key
        self.assertNotEqual(base, changed_prompt)
        self.assertNotEqual(base, changed_round)

    def test_idempotency_key_tracks_reference_image_content(self) -> None:
        """Same path, different bytes must produce a different key: the key hashes content, not filenames."""
        reference = self.fixture.reference("ref.png", b"first-bytes")
        plan = minimal_plan(
            items=[{"id": "item-01", "prompt": "p", "reference_images": [str(reference)]}]
        )
        first = self.fixture.validate(plan).items[0].idempotency_key
        reference.write_bytes(b"second-bytes")
        second = self.fixture.validate(plan).items[0].idempotency_key
        self.assertNotEqual(first, second)

    def test_missing_reference_image_is_reported(self) -> None:
        plan = minimal_plan(
            items=[{"id": "item-01", "prompt": "p", "reference_images": [str(self.fixture.base / "absent.png")]}]
        )
        result = self.fixture.validate(plan)
        self.assertFalse(result.ok)
        self.assertIn("plan_missing_reference_image", [error.code for error in result.errors])

    def test_duplicate_item_id_is_rejected(self) -> None:
        plan = minimal_plan(items=[{"id": "item-01", "prompt": "a"}, {"id": "item-01", "prompt": "b"}])
        result = self.fixture.validate(plan)
        self.assertIn("plan_duplicate_item_id", [error.code for error in result.errors])

    def test_whitespace_prompt_is_rejected(self) -> None:
        plan = minimal_plan(items=[{"id": "item-01", "prompt": "   \n  "}])
        result = self.fixture.validate(plan)
        self.assertIn("plan_empty_prompt", [error.code for error in result.errors])

    def test_size_and_quality_are_not_expressible(self) -> None:
        """The platform cannot honour these, so the plan must not pretend to ask for them."""
        for forbidden in ("size", "quality", "background", "n", "model"):
            with self.subTest(field=forbidden):
                plan = minimal_plan(items=[{"id": "item-01", "prompt": "p", forbidden: "anything"}])
                result = self.fixture.validate(plan)
                self.assertFalse(result.ok)
                self.assertEqual(result.errors[0].code, "plan_schema_invalid")

    def test_image_cap_is_enforced(self) -> None:
        items = [{"id": f"item-{n:02d}", "prompt": "p"} for n in range(3)]
        plan = minimal_plan(
            items=items,
            limits={"max_images": 2, "max_rounds": 5, "require_approval_before_run": True},
        )
        result = self.fixture.validate(plan)
        self.assertIn("plan_exceeds_max_images", [error.code for error in result.errors])

    def test_round_cap_is_enforced(self) -> None:
        plan = minimal_plan(
            round=4,
            limits={"max_images": 10, "max_rounds": 3, "require_approval_before_run": True},
        )
        result = self.fixture.validate(plan)
        self.assertIn("plan_exceeds_max_rounds", [error.code for error in result.errors])

    def test_approval_defaults_to_required_when_limits_are_absent(self) -> None:
        result = self.fixture.validate(minimal_plan())
        self.assertTrue(result.require_approval_before_run)

    def test_approval_cannot_be_waived(self) -> None:
        result = self.fixture.validate(
            minimal_plan(limits={"max_images": 5, "max_rounds": 2, "require_approval_before_run": False})
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0].code, "plan_schema_invalid")

    def test_legacy_plan_is_migrated_before_validation(self) -> None:
        legacy = {
            "schema_version": "1.0.0",
            "batch_id": "portrait-study",
            "round": 1,
            "items": [{"id": "item-01", "prompt": "legacy portrait"}],
        }
        result = self.fixture.validate(legacy)
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(result.require_approval_before_run)

    def test_validator_caps_match_the_published_schema(self) -> None:
        item_cap = SCHEMA["properties"]["items"]["maxItems"]
        limits = SCHEMA["$defs"]["batchLimits"]["properties"]
        self.assertEqual(plan_validator.DEFAULT_MAX_IMAGES, item_cap)
        self.assertEqual(plan_validator.DEFAULT_MAX_ROUNDS, limits["max_rounds"]["maximum"])
        self.assertEqual(
            plan_validator.MAX_REFERENCE_IMAGES,
            SCHEMA["$defs"]["batchItem"]["properties"]["reference_images"]["maxItems"],
        )

    def test_reference_hash_is_recorded(self) -> None:
        ref = self.fixture.reference("ref.png", b"known-bytes")
        plan = minimal_plan(items=[{"id": "item-01", "prompt": "p", "reference_images": [str(ref)]}])
        result = self.fixture.validate(plan)
        self.assertTrue(result.ok, result.errors)
        expected = hashlib.sha256(b"known-bytes").hexdigest()
        self.assertEqual(result.items[0].reference_sha256, (expected,))

    def test_human_label_policy_reaches_plan_result(self) -> None:
        result = self.fixture.validate(valid_plan_1_1())
        self.assertTrue(result.require_human_labels)

    def test_plan_hash_changes_when_reference_bytes_change(self) -> None:
        reference = self.fixture.reference("ref.png", _valid_png(1))
        plan = plan_with_reference(reference)
        first = self.fixture.validate(plan)
        reference.write_bytes(second_png())
        second = self.fixture.validate(plan)
        self.assertNotEqual(first.plan_sha256, second.plan_sha256)

    def test_semantically_identical_json_has_the_same_plan_hash(self) -> None:
        first = self.fixture.validate(plan_a())
        second = self.fixture.validate(same_plan_with_different_key_order())
        self.assertEqual(first.plan_sha256, second.plan_sha256)

    def test_legacy_plan_reports_migration_note(self) -> None:
        legacy = {
            "schema_version": "1.0.0",
            "batch_id": "portrait-study",
            "round": 1,
            "items": [{"id": "item-01", "prompt": "legacy portrait"}],
        }
        result = self.fixture.validate(legacy)
        self.assertEqual(
            result.migration_notes,
            (
                "migrated image batch 1.0.0 to 1.1.0",
                "migrated image batch 1.1.0 to 1.2.0",
                "migrated image batch 1.2.0 to 1.3.0",
            ),
        )


if __name__ == "__main__":
    unittest.main()
