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
import image_quality  # noqa: E402
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

    def test_versioned_multi_hash_records_distances_and_avoids_ahash_false_positive(self) -> None:
        first_path = self.fixture.base / "bars.png"
        second_path = self.fixture.base / "checker.png"
        _make_png(first_path, 32, 32, lambda x, y: (240, 240, 240, 255) if x % 4 < 2 else (20, 20, 20, 255))
        _make_png(second_path, 32, 32, lambda x, y: (240, 240, 240, 255) if x % 4 >= 2 else (20, 20, 20, 255))
        first, second = _item("frame-01"), _item("frame-02")
        receipts = {first.id: self.fixture.receipt(first, first_path), second.id: self.fixture.receipt(second, second_path)}
        policy = {"version": "multi-hash-v1", "thresholds": {"ahash": 2, "dhash": 3, "phash": 3}, "min_matches": 2}

        result = self.fixture.evaluate([first, second], receipts, near_duplicate_hamming_distance=None, near_duplicate_policy=policy)

        rows = {row["item_id"]: row for row in result.scores["deterministic_gates"]["per_item"]}
        evidence = rows[first.id]["near_duplicate_evidence"][0]
        self.assertEqual(evidence["policy_version"], "multi-hash-v1")
        self.assertEqual(result.scores["near_duplicate_policy"]["thresholds"], policy["thresholds"])
        self.assertEqual(set(evidence["distances"]), {"ahash", "dhash", "phash"})
        self.assertEqual(evidence["distances"]["ahash"], 0)
        self.assertGreater(evidence["distances"]["dhash"], 3)
        self.assertFalse(evidence["matched"])
        self.assertNotIn("near_duplicate_content", rows[first.id]["failures"])
        schema = json.loads((ROOT / "schemas/scores.schema.json").read_text())
        self.assertEqual(schema_lite.validate(result.scores, schema), [])

    def test_multi_hash_detects_small_variation_and_crop_evidence_is_explicit(self) -> None:
        base = self.fixture.base / "base.png"
        tint = self.fixture.base / "tint.png"
        crop = self.fixture.base / "crop.png"
        def colour(x, y):
            light = (x // 6 + y // 7) % 3 == 0 or (11 < x < 24 and 9 < y < 23)
            return (220, 220, 220, 255) if light else (30, 30, 30, 255)
        _make_png(base, 32, 32, colour)
        _make_png(tint, 32, 32, lambda x, y: tuple(min(255, c + 1) for c in colour(x, y)[:3]) + (255,))
        _make_png(crop, 24, 24, lambda x, y: colour(x + 4, y + 4))
        first, second = _item("frame-01"), _item("frame-02")
        receipts = {first.id: self.fixture.receipt(first, base), second.id: self.fixture.receipt(second, tint)}
        policy = {"version": "multi-hash-v1", "thresholds": {"ahash": 4, "dhash": 4, "phash": 4}, "min_matches": 2}
        result = self.fixture.evaluate([first, second], receipts, near_duplicate_hamming_distance=None, near_duplicate_policy=policy)
        evidence = result.scores["deterministic_gates"]["per_item"][0]["near_duplicate_evidence"][0]
        self.assertTrue(evidence["matched"])
        self.assertEqual(evidence["distances"], {"ahash": 0, "dhash": 0, "phash": 0})
        cropped_distances = image_quality.multi_hash_distances(image_quality.multi_hash(base), image_quality.multi_hash(crop))
        self.assertEqual(set(cropped_distances), {"ahash", "dhash", "phash"})
        self.assertTrue(any(value > 0 for value in cropped_distances.values()))
        self.assertGreater(cropped_distances["ahash"], 4)
        crop_receipt = self.fixture.receipt(second, crop)
        cropped = self.fixture.evaluate([first, second], {first.id: receipts[first.id], second.id: crop_receipt}, near_duplicate_hamming_distance=None, near_duplicate_policy={"version": "multi-hash-v1", "thresholds": {"ahash": 4, "dhash": 24, "phash": 30}, "min_matches": 2})
        crop_evidence = cropped.scores["deterministic_gates"]["per_item"][0]["near_duplicate_evidence"][0]
        self.assertTrue(crop_evidence["matched"])
        self.assertGreater(crop_evidence["distances"]["ahash"], 4)

    def test_plan_multi_hash_policy_is_versioned_and_exclusive(self) -> None:
        policy = {"version": "multi-hash-v1", "thresholds": {"ahash": 4, "dhash": 8, "phash": 8}, "min_matches": 2}
        plan = {"schema_version": "1.6.0", "batch_id": "quality-study", "round": 1, "judge_policy": {"min_dimension": 16, "reject_duplicates": True, "pass_threshold": 0.8, "require_human_labels": True, "near_duplicate_policy": policy}, "items": [{"id": "frame-01", "prompt": "student"}]}
        result = plan_validator.validate_plan(plan, base_dir=self.fixture.base)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.near_duplicate_policy, policy)
        plan["judge_policy"]["near_duplicate_hamming_distance"] = 4
        self.assertFalse(plan_validator.validate_plan(plan, base_dir=self.fixture.base).ok)

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

    def test_review_workspace_contains_verified_anchor_regions_filters_and_local_label_export(self) -> None:
        source = self.fixture.base / "portrait.png"
        _make_png(source, 32, 32, lambda _x, _y: (60, 100, 150, 255))
        anchor, current = _item("frame-01"), _item("frame-02")
        receipts = {item.id: self.fixture.receipt(item, source) for item in (anchor, current)}
        scores = self.fixture.evaluate([anchor, current], receipts).scores
        scores["reviewer_reports"] = [{
            "reviewer": {"id": "face", "version": "1.0.0", "capabilities": ["identity_embedding"]},
            "items": [{"item_id": current.id, "findings": [{
                "dimension": "character_identity", "score": 0.9, "confidence": 0.8,
                "evidence": "different hairline", "region": {"x": 0.2, "y": 0.1, "width": 0.3, "height": 0.4}, "uncertain": False,
            }]}], "authority": "advisory",
        }]
        scores["human_labels"] = [{"item_id": current.id, "label": "rejected", "reason": "hairline changed"}]
        summary = visual_summary.build_summary(receipts=receipts, scores=scores, destination_dir=self.fixture.destination, output_dir=self.fixture.base / "review", anchors={current.id: anchor.id})
        index = json.loads(Path(summary["storyboard_index"]).read_text())
        row = next(row for row in index["items"] if row["item_id"] == current.id)
        self.assertEqual(row["anchor_item_id"], anchor.id)
        self.assertEqual(row["findings"][0]["region"]["x"], 0.2)
        self.assertEqual(row["human_reason"], "hairline changed")
        self.assertEqual(row["disagreements"][0]["dimension"], "character_identity")
        page = Path(summary["contact_sheet"]).read_text()
        self.assertIn('name="dimension-filter"', page)
        self.assertIn('name="review-reason"', page)
        self.assertIn("download-review", page)
        self.assertIn("@media(max-width:390px)", page)
        self.assertIn(".compare{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))", page)
        self.assertIn(".grid,.compare{grid-template-columns:minmax(0,1fr)}", page)
        self.assertEqual(list((self.fixture.base / "review").glob("*.png")), [])

    def test_review_html_escapes_untrusted_finding_text(self) -> None:
        source = self.fixture.base / "portrait.png"
        _make_png(source, 32, 32, lambda _x, _y: (60, 100, 150, 255))
        item = _item("frame-01")
        receipt = self.fixture.receipt(item, source)
        scores = self.fixture.evaluate([item], {item.id: receipt}).scores
        scores["reviewer_reports"] = [{"reviewer": {"id": "face", "version": "1.0.0"}, "items": [{"item_id": item.id, "findings": [{"dimension": "character_identity", "score": 0.1, "confidence": 0.9, "evidence": "</script><script>alert(1)</script>", "region": None, "uncertain": False}]}]}]
        summary = visual_summary.build_summary(receipts={item.id: receipt}, scores=scores, destination_dir=self.fixture.destination, output_dir=self.fixture.base / "review")
        page = Path(summary["contact_sheet"]).read_text()
        self.assertNotIn("</script><script>alert(1)</script>", page)
        self.assertIn("&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_review_anchor_must_be_a_verified_receipt(self) -> None:
        source = self.fixture.base / "portrait.png"
        _make_png(source, 32, 32, lambda _x, _y: (60, 100, 150, 255))
        item = _item("frame-01")
        receipt = self.fixture.receipt(item, source)
        scores = self.fixture.evaluate([item], {item.id: receipt}).scores
        with self.assertRaisesRegex(ValueError, "anchor"):
            visual_summary.build_summary(receipts={item.id: receipt}, scores=scores, destination_dir=self.fixture.destination, output_dir=self.fixture.base / "review", anchors={item.id: "missing"})

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
        self.assertFalse(report["overall"]["sample_sufficient"])
        self.assertEqual(report["threshold_candidates"], [])
        schema = json.loads((ROOT / "schemas/calibration_report.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema_lite.validate(report, schema), [])

    def test_calibration_requires_sample_sufficiency_and_reports_strata_and_drift(self) -> None:
        rows = [{"item_id": f"frame-{i:02}", "score": 0.9, "dimensions": []} for i in range(1, 5)]
        scores = {
            "batch_id": "quality-study", "round": 1, "pass_threshold": 0.8,
            "advisory": {"items": rows},
            "human_labels": [{"item_id": row["item_id"], "label": "rejected"} for row in rows],
            "reviewer_reports": [{"reviewer": {"id": "face", "version": "2.0.0"}, "items": []}],
        }
        context = {row["item_id"]: {"model": "model-a", "provider": "provider-a", "style": "storybook", "shot_type": "close-up"} for row in rows}
        report = calibration.build_report(scores, min_samples=5, item_context=context, approved_baseline={"approved": True, "reviewer_id": "face", "reviewer_version": "1.0.0", "false_positive_rate": 0.0, "min_samples": 4}, drift_tolerance=0.1)
        self.assertFalse(report["overall"]["sample_sufficient"])
        self.assertEqual(report["threshold_candidates"], [])
        self.assertEqual(report["overall"]["false_positive_rate"]["interval"]["method"], "wilson-95-v1")
        interval = report["overall"]["false_positive_rate"]["interval"]
        self.assertLessEqual(0, interval["low"])
        self.assertLessEqual(interval["low"], interval["high"])
        self.assertLessEqual(interval["high"], 1)
        self.assertEqual(report["strata"][0]["axis"], "model")
        self.assertEqual(report["strata"][0]["value"], "model-a")
        self.assertTrue(report["drift"]["review_required"])
        self.assertFalse(report["threshold_changed"])

    def test_unapproved_drift_baseline_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "approved baseline"):
            calibration.build_report({"batch_id": "quality-study", "round": 1, "pass_threshold": 0.8}, approved_baseline={"reviewer_id": "face", "reviewer_version": "1.0.0", "false_positive_rate": 0.0, "min_samples": 4})

    def test_calibration_keeps_unobserved_error_rates_null(self) -> None:
        scores = {"batch_id": "quality-study", "round": 1, "pass_threshold": 0.8, "advisory": {"items": [{"item_id": "frame-01", "score": 0.9}]}, "human_labels": [{"item_id": "frame-01", "label": "approved"}]}
        report = calibration.build_report(scores, min_samples=2)
        self.assertIsNone(report["overall"]["false_positive_rate"]["value"])
        self.assertIsNone(report["overall"]["false_positive_rate"]["interval"]["low"])

    def test_human_label_reason_survives_evaluation_and_schema(self) -> None:
        source = self.fixture.base / "portrait.png"
        _make_png(source, 32, 32, lambda _x, _y: (60, 100, 150, 255))
        item = _item("frame-01")
        receipt = self.fixture.receipt(item, source)
        scores = self.fixture.evaluate([item], {item.id: receipt}, human_labels={item.id: {"label": "rejected", "reason": "missing red book"}}).scores
        self.assertEqual(scores["human_labels"][0]["reason"], "missing red book")
        schema = json.loads((ROOT / "schemas/scores.schema.json").read_text())
        self.assertEqual(schema_lite.validate(scores, schema), [])


if __name__ == "__main__":
    unittest.main()
