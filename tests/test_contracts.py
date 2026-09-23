import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
sys.path.insert(0, str(ROOT / "scripts"))

import schema_lite  # noqa: E402
PLUGIN_ID = "image-factory"
REPOSITORY = "https://github.com/full-aigc-plugins/image-factory-plugin"
JSON_SCHEMA = "https://json-schema.org/draft/2020-12/schema"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

SCHEMA_FILES = (
    "image_batch.schema.json",
    "artifact_receipt.schema.json",
    "factory_job.schema.json",
    "scores.schema.json",
)

# Governed by codex-rs ext/image-generation/src/tool.rs:59 (MAX_EDIT_IMAGES).
PLATFORM_MAX_REFERENCE_IMAGES = 5
# Governed by the platform boundary documented in the architecture: one image per tool call.
PLATFORM_IMAGES_PER_CALL = 1


def load_schema(name: str) -> dict:
    target = SCHEMA_DIR / name
    if not target.is_file():
        raise AssertionError(f"missing schema: {name}")
    return json.loads(target.read_text(encoding="utf-8"))


def iter_subschemas(node: dict):
    """Yield every subschema reachable from the root through schema positions only."""
    yield node
    for container in ("properties", "$defs"):
        children = node.get(container)
        if isinstance(children, dict):
            for child in children.values():
                if isinstance(child, dict):
                    yield from iter_subschemas(child)
    items = node.get("items")
    if isinstance(items, dict):
        yield from iter_subschemas(items)


class SchemaSupportTests(unittest.TestCase):
    def test_no_schema_uses_a_keyword_the_checker_cannot_enforce(self) -> None:
        """A keyword the checker silently ignored would be a rule enforced nowhere."""
        for name in SCHEMA_FILES:
            for subschema in iter_subschemas(load_schema(name)):
                with self.subTest(schema=name, title=subschema.get("title")):
                    unsupported = set(subschema) - schema_lite.SUPPORTED_KEYWORDS
                    self.assertEqual(unsupported, set(), f"{name}: unsupported keywords {unsupported}")

    def test_no_schema_uses_an_unsupported_format(self) -> None:
        for name in SCHEMA_FILES:
            for subschema in iter_subschemas(load_schema(name)):
                declared = subschema.get("format")
                if declared is not None:
                    with self.subTest(schema=name, format=declared):
                        self.assertIn(declared, schema_lite.SUPPORTED_FORMATS)


class SchemaContractTests(unittest.TestCase):
    def test_every_schema_is_closed_draft_2020_12(self) -> None:
        for name in SCHEMA_FILES:
            with self.subTest(schema=name):
                schema = load_schema(name)
                self.assertEqual(schema["$schema"], JSON_SCHEMA)
                self.assertEqual(schema["$id"], f"{REPOSITORY}/schemas/{name}")
                self.assertIs(schema["additionalProperties"], False)
                self.assertIn("required", schema)
                self.assertTrue(schema["required"], "required must not be empty")
                for required in schema["required"]:
                    self.assertIn(required, schema["properties"], f"{name}: {required} not declared")

    def test_batch_plan_shape(self) -> None:
        schema = load_schema("image_batch.schema.json")
        props = schema["properties"]
        self.assertEqual(schema["required"], ["schema_version", "batch_id", "round", "items"])
        self.assertEqual(props["schema_version"]["const"], "1.3.0")
        self.assertEqual(props["batch_id"]["pattern"], "^[a-z0-9][a-z0-9_-]{2,63}$")
        self.assertEqual(props["round"]["minimum"], 1)
        self.assertIsInstance(props["schema_version"]["const"], str)

        items = props["items"]
        self.assertEqual(items["minItems"], 1)
        self.assertEqual(items["maxItems"], 200)
        item = schema["$defs"]["batchItem"]
        self.assertIs(item["additionalProperties"], False)
        self.assertEqual(item["required"], ["id", "prompt"])
        self.assertEqual(item["properties"]["reference_images"]["maxItems"], PLATFORM_MAX_REFERENCE_IMAGES)
        self.assertEqual(item["properties"]["id"]["pattern"], "^[a-z0-9][a-z0-9_-]{0,63}$")
        self.assertEqual(item["properties"]["prompt"]["minLength"], 1)
        checks = item["properties"]["pixel_checks"]
        self.assertEqual(checks["maxItems"], 8)
        self.assertEqual(checks["items"]["required"], ["kind"])
        self.assertIs(checks["items"]["additionalProperties"], False)
        self.assertEqual(
            checks["items"]["properties"]["kind"]["enum"],
            ["corner-colour", "min-margin", "ink-colour"],
        )

        limits = schema["$defs"]["batchLimits"]
        self.assertIs(limits["additionalProperties"], False)
        self.assertEqual(limits["required"], ["max_images", "max_rounds", "require_approval_before_run"])
        self.assertEqual(limits["properties"]["require_approval_before_run"], {"const": True})

    def test_image_plan_1_3_requires_both_human_gates(self) -> None:
        schema = load_schema("image_batch.schema.json")
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.3.0")
        limits = schema["$defs"]["batchLimits"]
        policy = schema["$defs"]["judgePolicy"]
        self.assertEqual(limits["properties"]["require_approval_before_run"], {"const": True})
        self.assertIn("require_human_labels", policy["required"])
        self.assertEqual(policy["properties"]["require_human_labels"], {"const": True})

    def test_artifact_receipt_shape(self) -> None:
        schema = load_schema("artifact_receipt.schema.json")
        props = schema["properties"]
        for field in (
            "schema_version",
            "plugin_id",
            "batch_id",
            "item_id",
            "round",
            "artifact_id",
            "path",
            "sha256",
            "bytes",
            "width",
            "height",
            "prompt_sha256",
            "idempotency_key",
            "source",
            "collected_at",
        ):
            self.assertIn(field, schema["required"], field)
        self.assertEqual(props["plugin_id"]["const"], PLUGIN_ID)
        self.assertEqual(props["schema_version"]["const"], "1.0.0")
        self.assertEqual(props["sha256"]["pattern"], "^[0-9a-f]{64}$")
        self.assertEqual(props["prompt_sha256"]["pattern"], "^[0-9a-f]{64}$")
        self.assertEqual(props["idempotency_key"]["pattern"], "^[0-9a-f]{64}$")
        self.assertEqual(props["bytes"]["minimum"], 1)
        self.assertEqual(props["width"]["minimum"], 1)
        self.assertEqual(props["height"]["minimum"], 1)

        source = props["source"]
        self.assertIs(source["additionalProperties"], False)
        self.assertEqual(source["required"], ["kind", "session_id", "call_id"])
        self.assertEqual(source["properties"]["kind"]["const"], "codex_image_gen")
        self.assertIn("model_reported", source["properties"])
        self.assertIn("null", source["properties"]["model_reported"]["type"])

    def test_factory_job_state_machine_shape(self) -> None:
        schema = load_schema("factory_job.schema.json")
        props = schema["properties"]
        self.assertEqual(
            props["state"]["enum"],
            [
                "Draft",
                "PlanValidated",
                "Approved",
                "Running",
                "Evaluated",
                "PendingApproval",
                "Optimized",
                "Accepted",
                "Completed",
                "Partial",
                "Failed",
                "Unknown",
            ],
        )
        error_categories = props["error_category"]["enum"]
        self.assertIn(None, error_categories, "a healthy job has no error category")
        self.assertEqual(
            [category for category in error_categories if category is not None],
            [
                "capability_unavailable",
                "codex_missing",
                "quota_exceeded",
                "timeout",
                "generation_failed",
                "artifact_missing",
                "hash_mismatch",
                "duplicate_artifact",
                "plan_invalid",
                "approval_required",
                "job_already_running",
                "recovery_required",
                "unknown",
            ],
        )
        self.assertEqual(props["revision"]["minimum"], 1)
        self.assertEqual(props["schema_version"]["const"], "1.2.0")

    def test_factory_job_1_2_exposes_transaction_fields(self) -> None:
        schema = load_schema("factory_job.schema.json")
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.2.0")
        numeric = schema["properties"]["numeric_history"]
        self.assertEqual(numeric["items"]["$ref"], "#/$defs/numericEvaluation")
        entry = schema["$defs"]["numericEvaluation"]
        self.assertIs(entry["additionalProperties"], False)
        self.assertIn(
            "best_score",
            entry["required"],
            "a round without numbers must record that fact explicitly",
        )
        self.assertEqual(entry["properties"]["best_score"]["type"], ["number", "null"])
        self.assertIn("PendingApproval", schema["properties"]["state"]["enum"])
        self.assertIn("Accepted", schema["properties"]["state"]["enum"])
        item = schema["$defs"]["jobItem"]
        self.assertIn("Attempting", item["properties"]["state"]["enum"])
        self.assertIn("Unknown", item["properties"]["state"]["enum"])
        self.assertIn("attempt_id", item["required"])
        self.assertFalse(schema["$defs"]["approvalRecord"]["additionalProperties"])

    def test_factory_job_transaction_records_are_closed_and_typed(self) -> None:
        schema = load_schema("factory_job.schema.json")
        for name in (
            "batchRecord",
            "approvalRecord",
            "approvalLedger",
            "evaluationRecord",
            "optimizationRecord",
            "jobItem",
        ):
            with self.subTest(definition=name):
                self.assertIs(schema["$defs"][name]["additionalProperties"], False)
        self.assertEqual(
            schema["$defs"]["batchRecord"]["properties"]["plan_sha256"]["pattern"],
            "^[0-9a-f]{64}$",
        )
        self.assertEqual(
            schema["$defs"]["approvalRecord"]["properties"]["approved_at"]["format"],
            "date-time",
        )

    def test_scores_shape(self) -> None:
        schema = load_schema("scores.schema.json")
        props = schema["properties"]
        self.assertEqual(
            schema["required"],
            ["schema_version", "batch_id", "round", "pass_threshold", "deterministic_gates", "advisory", "human_labels", "decision"],
        )
        self.assertEqual(props["schema_version"]["const"], "1.1.0")
        self.assertEqual(props["decision"]["enum"], ["pass", "fail", "pending_approval"])
        self.assertEqual(props["advisory"]["properties"]["enabled"]["type"], "boolean")
        item_score = schema["$defs"]["advisoryScore"]
        self.assertEqual(item_score["properties"]["score"]["minimum"], 0)
        self.assertEqual(item_score["properties"]["score"]["maximum"], 1)
        self.assertEqual(
            schema["$defs"]["humanLabel"]["properties"]["label"]["enum"],
            ["approved", "rejected", "unlabeled"],
        )
        dimensions = item_score["properties"]["dimensions"]
        self.assertEqual(dimensions["maxItems"], 16)
        dimension = dimensions["items"]
        self.assertEqual(dimension["required"], ["name", "score"])
        self.assertEqual(dimension["properties"]["name"]["maxLength"], 64)
        self.assertEqual(dimension["properties"]["score"]["minimum"], 0)
        self.assertEqual(dimension["properties"]["score"]["maximum"], 1)
        self.assertEqual(dimension["properties"]["evidence"]["maxLength"], 2000)
        self.assertIn("complete", dimension["properties"])
        gate = schema["$defs"]["gateResult"]
        self.assertEqual(gate["required"], ["item_id", "passed", "failures"])
        # Widened by add-declared-pixel-checks: a declared pixel check has one
        # true answer just like the five original gates, so it joins their tier.
        self.assertEqual(gate["properties"]["failures"]["items"]["enum"], [
            "not_a_png",
            "below_min_dimension",
            "duplicate_content",
            "hash_mismatch",
            "missing_artifact",
            "failed_pixel_check",
        ])
        detail = gate["properties"]["pixel_checks"]["items"]
        self.assertEqual(detail["required"], ["kind", "passed", "measured", "expected"])
        self.assertIs(detail["additionalProperties"], False)
        self.assertEqual(
            detail["properties"]["kind"]["enum"],
            ["corner-colour", "min-margin", "ink-colour"],
        )

    def test_platform_limit_is_recorded_not_assumed(self) -> None:
        """The plugin must not promise size/quality control the platform lacks."""
        schema = load_schema("image_batch.schema.json")
        item_props = schema["$defs"]["batchItem"]["properties"]
        for forbidden in ("size", "quality", "background", "n", "model"):
            self.assertNotIn(
                forbidden,
                item_props,
                f"batch items must not accept {forbidden!r}: the built-in tool hardcodes it",
            )
        limits = schema["$defs"]["batchLimits"]["properties"]
        self.assertEqual(limits["max_images"]["maximum"], 200)
        self.assertEqual(PLATFORM_IMAGES_PER_CALL, 1)


if __name__ == "__main__":
    unittest.main()
