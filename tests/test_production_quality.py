import json
import struct
import sys
import tempfile
import unittest
import zlib
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import artifact_collector  # noqa: E402
import calibration  # noqa: E402
import evaluator  # noqa: E402
import plan_validator  # noqa: E402
import provenance  # noqa: E402
import reviewer_adapter  # noqa: E402
import schema_lite  # noqa: E402
import visual_summary  # noqa: E402


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _make_png(path: Path, width: int, height: int, rgba) -> None:
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw += bytes(rgba(x, y))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + b"".join(
            (
                _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
                _chunk(b"IDAT", zlib.compress(bytes(raw))),
                _chunk(b"IEND", b""),
            )
        )
    )


def _item(item_id: str, *, series: bool = False, ratio=(0.9, 1.1)) -> plan_validator.PlanItem:
    prompt = f"portrait {item_id}"
    return plan_validator.PlanItem(
        id=item_id,
        prompt=prompt,
        round=1,
        reference_images=(),
        reference_sha256=(),
        idempotency_key=plan_validator.compute_idempotency_key(
            batch_id="quality-study",
            item_id=item_id,
            round_number=1,
            prompt=prompt,
            reference_sha256=(),
        ),
        entity_ids=("student",) if series else (),
        aspect_ratio_range=ratio,
    )


class QualityFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.destination = self.base / "out"
        self.destination.mkdir()

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def receipt(self, item: plan_validator.PlanItem, source: Path) -> dict:
        relative = Path("quality-study") / "round-1" / f"{item.id}.png"
        target = self.destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        width, height = artifact_collector.parse_png_size(target) or (0, 0)
        return {
            "schema_version": "1.1.0",
            "plugin_id": "image-factory",
            "batch_id": "quality-study",
            "item_id": item.id,
            "round": 1,
            "artifact_id": f"{item.id}-r1-{item.idempotency_key[:12]}",
            "path": relative.as_posix(),
            "sha256": artifact_collector.file_sha256(target),
            "bytes": target.stat().st_size,
            "width": width,
            "height": height,
            "prompt_sha256": "c" * 64,
            "idempotency_key": item.idempotency_key,
            "source": {
                "kind": "codex_image_gen",
                "session_id": "session-a",
                "call_id": item.id,
                "model_reported": None,
            },
            "provenance": provenance.build_provenance(
                plugin_revision="abc123",
                capability_report={"verdict": "available", "reasons": ["verified"]},
                consistency_profile_sha256="d" * 64,
            ),
            "collected_at": "2026-09-23T00:00:00Z",
        }

    def evaluate(self, items, receipts, **overrides):
        arguments = {
            "batch_id": "quality-study",
            "round_number": 1,
            "items": tuple(items),
            "receipts": receipts,
            "destination_dir": self.destination,
            "min_dimension": 8,
            "reject_duplicates": True,
            "near_duplicate_hamming_distance": 2,
            "pass_threshold": 0.8,
            "advisory_enabled": False,
            "require_human_labels": False,
        }
        arguments.update(overrides)
        return evaluator.evaluate_batch(**arguments)


class DeterministicQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = QualityFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_declared_aspect_ratio_is_a_file_derived_gate(self) -> None:
        source = self.fixture.base / "wide.png"
        _make_png(source, 32, 16, lambda _x, _y: (120, 80, 20, 255))
        item = _item("frame-01")
        receipt = self.fixture.receipt(item, source)

        result = self.fixture.evaluate([item], {item.id: receipt})

        gate = result.scores["deterministic_gates"]["per_item"][0]
        self.assertIn("aspect_ratio_out_of_range", gate["failures"])
        self.assertEqual(gate["aspect_ratio"]["measured"], 2.0)
        self.assertEqual(gate["aspect_ratio"]["expected"], {"min": 0.9, "max": 1.1})

    def test_near_duplicate_hash_flags_every_participant(self) -> None:
        first_path = self.fixture.base / "first.png"
        second_path = self.fixture.base / "second.png"
        _make_png(first_path, 32, 32, lambda x, y: (240 if x < 16 else 20, y, 20, 255))
        _make_png(second_path, 32, 32, lambda x, y: (239 if x < 16 else 21, y, 21, 255))
        first = replace(_item("frame-01"), aspect_ratio_range=None)
        second = replace(_item("frame-02"), aspect_ratio_range=None)
        receipts = {
            first.id: self.fixture.receipt(first, first_path),
            second.id: self.fixture.receipt(second, second_path),
        }

        result = self.fixture.evaluate([first, second], receipts)

        gates = {
            row["item_id"]: row for row in result.scores["deterministic_gates"]["per_item"]
        }
        self.assertIn("near_duplicate_content", gates[first.id]["failures"])
        self.assertIn("near_duplicate_content", gates[second.id]["failures"])
        self.assertEqual(gates[first.id]["near_duplicate_with"], [second.id])
        self.assertEqual(gates[second.id]["near_duplicate_with"], [first.id])

    def test_plan_declares_quality_gates_without_changing_generation_identity(self) -> None:
        plan = {
            "schema_version": "1.4.0",
            "batch_id": "quality-study",
            "round": 1,
            "judge_policy": {
                "min_dimension": 64,
                "reject_duplicates": True,
                "near_duplicate_hamming_distance": 4,
                "pass_threshold": 0.8,
                "require_human_labels": True,
            },
            "items": [
                {
                    "id": "frame-01",
                    "prompt": "student writing",
                    "aspect_ratio_range": {"min": 0.95, "max": 1.05},
                }
            ],
        }
        result = plan_validator.validate_plan(plan, base_dir=self.fixture.base)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.near_duplicate_hamming_distance, 4)
        self.assertEqual(result.items[0].aspect_ratio_range, (0.95, 1.05))
        identity = result.items[0].idempotency_key
        plan["items"][0]["aspect_ratio_range"] = {"min": 0.9, "max": 1.1}
        changed = plan_validator.validate_plan(plan, base_dir=self.fixture.base)
        self.assertEqual(changed.items[0].idempotency_key, identity)
        self.assertNotEqual(changed.plan_sha256, result.plan_sha256)

    def test_plan_rejects_an_inverted_aspect_ratio_range(self) -> None:
        plan = {
            "schema_version": "1.4.0",
            "batch_id": "quality-study",
            "round": 1,
            "items": [
                {
                    "id": "frame-01",
                    "prompt": "student writing",
                    "aspect_ratio_range": {"min": 2.0, "max": 1.0},
                }
            ],
        }
        result = plan_validator.validate_plan(plan, base_dir=self.fixture.base)
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0].code, "plan_aspect_ratio_range_invalid")


class AdvisoryQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = QualityFixture()
        self.addCleanup(self.fixture.cleanup)
        self.source = self.fixture.base / "portrait.png"
        _make_png(self.source, 32, 32, lambda _x, _y: (60, 100, 150, 255))
        self.item = _item("frame-01", series=True)
        self.receipt = self.fixture.receipt(self.item, self.source)

    def test_series_review_rejects_unknown_dimension_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "closed series dimensions"):
            self.fixture.evaluate(
                [self.item],
                {self.item.id: self.receipt},
                advisory={
                    self.item.id: {
                        "score": 0.9,
                        "dimensions": [
                            {"name": "vibes", "score": 0.9, "evidence": "blue coat visible"}
                        ],
                    }
                },
            )

    def test_text_finding_remains_advisory_and_blank_evidence_cannot_drive_rework(self) -> None:
        result = self.fixture.evaluate(
            [self.item],
            {self.item.id: self.receipt},
            advisory_enabled=True,
            advisory={
                self.item.id: {
                    "score": 0.4,
                    "reason": "possible text and uncertain identity",
                    "dimensions": [
                        {"name": "text_absence", "score": 0.2, "evidence": "OCR saw ABC"},
                        {"name": "character_identity", "score": 0.1, "evidence": "   "},
                    ],
                }
            },
        )

        self.assertEqual(result.scores["deterministic_gates"]["per_item"][0]["failures"], [])
        dimensions = result.scores["advisory"]["items"][0]["dimensions"]
        self.assertTrue(dimensions[0]["complete"])
        self.assertFalse(dimensions[1]["complete"])
        self.assertEqual(result.scores["decision"], "pending_approval")

    def test_versioned_reviewer_cannot_override_a_human_rejection(self) -> None:
        report = reviewer_adapter.adapt(
            {
                "schema_version": "1.0.0",
                "batch_id": "quality-study",
                "round": 1,
                "reviewer": {
                    "id": "identity-reviewer",
                    "version": "1.0.0",
                    "capabilities": ["identity_embedding"],
                    "model": None,
                    "provider": None,
                    "confidence_threshold": 0.7,
                },
                "items": [
                    {
                        "item_id": "frame-01",
                        "findings": [
                            {
                                "dimension": "character_identity",
                                "score": 0.99,
                                "confidence": 0.99,
                                "evidence": "identity anchor and frame align",
                                "region": None,
                            }
                        ],
                    }
                ],
            }
        )
        result = self.fixture.evaluate(
            [self.item],
            {self.item.id: self.receipt},
            advisory_enabled=True,
            advisory=reviewer_adapter.merge_advisory([report]),
            human_labels={self.item.id: "rejected"},
            reviewer_reports=[report],
        )

        self.assertEqual(result.scores["decision"], "fail")
        self.assertEqual(result.scores["reviewer_reports"][0]["authority"], "advisory")
        schema = json.loads((ROOT / "schemas/scores.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema_lite.validate(result.scores, schema), [])


class EvidenceProductTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = QualityFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_receipt_provenance_uses_null_for_unobserved_versions(self) -> None:
        row = provenance.build_provenance(
            plugin_revision="abc123",
            capability_report={"verdict": "available", "reasons": ["verified"]},
            consistency_profile_sha256="d" * 64,
        )
        self.assertEqual(row["plugin_revision"], "abc123")
        self.assertIsNone(row["host_version"])
        self.assertIsNone(row["codex_version"])
        self.assertIsNone(row["reviewer_version"])
        self.assertRegex(row["capability_signature"], r"^[0-9a-f]{64}$")
        self.assertEqual(row["consistency_profile_sha256"], "d" * 64)

    def test_visual_summary_is_deterministic_and_rebuildable_without_copying_images(self) -> None:
        source = self.fixture.base / "portrait.png"
        _make_png(source, 32, 32, lambda _x, _y: (60, 100, 150, 255))
        item = replace(_item("frame-01"), aspect_ratio_range=None)
        receipt = self.fixture.receipt(item, source)
        scores = self.fixture.evaluate([item], {item.id: receipt}).scores
        summary_dir = self.fixture.base / "summary"

        first = visual_summary.build_summary(
            receipts={item.id: receipt},
            scores=scores,
            destination_dir=self.fixture.destination,
            output_dir=summary_dir,
        )
        first_html = Path(first["contact_sheet"]).read_bytes()
        first_index = Path(first["storyboard_index"]).read_bytes()
        self.assertEqual(list(summary_dir.glob("*.png")), [])
        for target in summary_dir.iterdir():
            target.unlink()

        rebuilt = visual_summary.build_summary(
            receipts={item.id: receipt},
            scores=scores,
            destination_dir=self.fixture.destination,
            output_dir=summary_dir,
        )
        self.assertEqual(Path(rebuilt["contact_sheet"]).read_bytes(), first_html)
        self.assertEqual(Path(rebuilt["storyboard_index"]).read_bytes(), first_index)
        index = json.loads(first_index)
        self.assertEqual(index["items"][0]["sha256"], receipt["sha256"])

    def test_calibration_exposes_disagreements_without_changing_threshold(self) -> None:
        scores = {
            "batch_id": "quality-study",
            "round": 1,
            "pass_threshold": 0.8,
            "advisory": {
                "enabled": True,
                "items": [
                    {
                        "item_id": "frame-01",
                        "score": 0.9,
                        "dimensions": [
                            {
                                "name": "character_identity",
                                "score": 0.9,
                                "evidence": "same scar and coat",
                                "complete": True,
                            },
                            {
                                "name": "style",
                                "score": 0.1,
                                "complete": False,
                            },
                        ],
                    },
                    {"item_id": "frame-02", "score": 0.2, "dimensions": []},
                ],
            },
            "human_labels": [
                {"item_id": "frame-01", "label": "rejected", "at": "2026-09-23T00:00:00Z"},
                {"item_id": "frame-02", "label": "approved", "at": "2026-09-23T00:00:01Z"},
            ],
        }

        report = calibration.build_report(scores)

        self.assertEqual(report["configured_threshold"], 0.8)
        self.assertEqual(report["overall"]["confusion"], {"tp": 0, "fp": 1, "tn": 0, "fn": 1})
        self.assertEqual(report["overall"]["disagreements"], 2)
        self.assertEqual(report["dimensions"][0]["name"], "character_identity")
        self.assertNotIn("style", {row["name"] for row in report["dimensions"]})
        self.assertTrue(report["threshold_candidates"])
        schema = json.loads((ROOT / "schemas/calibration_report.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema_lite.validate(report, schema), [])


if __name__ == "__main__":
    unittest.main()
