import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import continuity_benchmark  # noqa: E402
import image_factory_cli  # noqa: E402
import optimizer  # noqa: E402
import plan_validator  # noqa: E402
import reviewer_adapter  # noqa: E402
import schema_lite  # noqa: E402


def benchmark_pack(shot_count: int = 4, minimum_sample_size: int = 3) -> dict:
    shots = []
    for index in range(shot_count):
        shots.append(
            {
                "id": f"frame-{index + 1:02d}",
                "prompt": f"勤能补拙故事第 {index + 1} 幕",
                "coverage": {
                    "viewpoint": "front" if index == 0 else "side",
                    "distance": "close" if index < 2 else "wide",
                    "occluded": index == 2,
                    "time_of_day": "day" if index < 2 else "night",
                    "emotion": "focused" if index < 3 else "confident",
                },
            }
        )
    return {
        "schema_version": "1.0.0",
        "benchmark_id": "diligence-story",
        "title": "勤能补拙连续性基准",
        "evidence_tier": "synthetic",
        "minimum_sample_size": minimum_sample_size,
        "shots": shots,
    }


def label(value: str, evidence: str | None = None) -> dict:
    return {"label": value, "evidence": evidence}


def benchmark_run(*, prompt_strategy: str = "structured-state-v1") -> dict:
    dimensions = {
        "character_identity": label("accepted"),
        "hairstyle": label("accepted"),
        "age": label("accepted"),
        "wardrobe": label("accepted"),
        "core_props": label("unlabeled"),
        "scene_state": label("accepted"),
    }
    return {
        "schema_version": "1.0.0",
        "run_id": f"run-{prompt_strategy}",
        "benchmark_id": "diligence-story",
        "evidence_tier": "synthetic",
        "model": "fixture-model",
        "provider": "fixture-provider",
        "prompt_strategy": prompt_strategy,
        "first_pass": True,
        "rework_rounds": 0,
        "cost_usd": None,
        "elapsed_seconds": None,
        "labels": [
            {"shot_id": f"frame-{index:02d}", "dimensions": copy.deepcopy(dimensions)}
            for index in range(1, 5)
        ],
    }


def story_plan() -> dict:
    return {
        "schema_version": "1.5.0",
        "batch_id": "diligence-story",
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
        "consistency_profile": {
            "mode": "series",
            "style_bible": "温暖的中国儿童绘本，水彩纸纹理",
            "entities": [
                {
                    "id": "student",
                    "kind": "character",
                    "description": "十二岁学生",
                    "fixed_traits": ["圆脸", "短黑发", "中等身材"],
                }
            ],
            "story_state": {
                "permanent_locks": [
                    {"path": "character.student.hair", "value": "short black hair"},
                    {"path": "character.student.age", "value": "12"},
                ],
                "scenes": [
                    {
                        "id": "study-room",
                        "locks": [
                            {"path": "wardrobe.student", "value": "blue jacket"},
                            {"path": "prop.desk", "value": "dark wooden desk"},
                        ],
                    }
                ],
                "variables": [
                    {"path": "prop.book.state", "initial_value": "closed"},
                    {"path": "character.student.pose", "initial_value": "seated"},
                ],
            },
        },
        "items": [
            {
                "id": "frame-01",
                "prompt": "学生开始练字",
                "entity_ids": ["student"],
                "scene_id": "study-room",
            },
            {
                "id": "frame-02",
                "prompt": "学生翻开书继续练习",
                "entity_ids": ["student"],
                "scene_id": "study-room",
                "state_transitions": [
                    {"path": "prop.book.state", "from": "closed", "to": "open"}
                ],
            },
        ],
    }


def reviewer_report() -> dict:
    return {
        "schema_version": "1.0.0",
        "batch_id": "diligence-story",
        "round": 1,
        "reviewer": {
            "id": "local-identity-reviewer",
            "version": "1.2.0",
            "capabilities": ["identity_embedding", "wardrobe_similarity"],
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
                        "score": 0.4,
                        "confidence": 0.55,
                        "evidence": "脸型与身份基准的下颌轮廓差异明显",
                        "region": {"x": 0.2, "y": 0.1, "width": 0.3, "height": 0.4},
                    },
                    {
                        "dimension": "wardrobe",
                        "score": 0.9,
                        "confidence": 0.95,
                        "evidence": "蓝色外套的领口与袖口均匹配",
                        "region": None,
                    },
                ],
            }
        ],
    }


class ContinuityBenchmarkTests(unittest.TestCase):
    def test_bundled_story_groups_fix_four_eight_and_twelve_shots(self) -> None:
        benchmark_dir = ROOT / "data" / "benchmarks"
        observed_counts = set()
        for path in sorted(benchmark_dir.glob("diligence-story-*.synthetic.json")):
            pack = continuity_benchmark.validate_pack(
                json.loads(path.read_text(encoding="utf-8"))
            )
            observed_counts.add(len(pack["shots"]))
            coverage = [shot["coverage"] for shot in pack["shots"]]
            self.assertIn("front", {row["viewpoint"] for row in coverage})
            self.assertIn("side", {row["viewpoint"] for row in coverage})
            self.assertIn("wide", {row["distance"] for row in coverage})
            self.assertIn(True, {row["occluded"] for row in coverage})
            self.assertIn("day", {row["time_of_day"] for row in coverage})
            self.assertIn("night", {row["time_of_day"] for row in coverage})
            self.assertGreaterEqual(len({row["emotion"] for row in coverage}), 3)
            self.assertEqual(pack["evidence_tier"], "synthetic")
        self.assertEqual(observed_counts, {4, 8, 12})

    def test_only_four_eight_or_twelve_shots_are_allowed(self) -> None:
        for count in (4, 8, 12):
            continuity_benchmark.validate_pack(benchmark_pack(count))
        with self.assertRaisesRegex(ValueError, "4, 8, or 12"):
            continuity_benchmark.validate_pack(benchmark_pack(5))

    def test_missing_labels_are_not_counted_as_passes(self) -> None:
        report = continuity_benchmark.summarize(benchmark_pack(), [benchmark_run()])
        props = report["overall"]["dimension_metrics"]["core_props"]
        self.assertEqual(props["labeled_count"], 0)
        self.assertEqual(props["unlabeled_count"], 4)
        self.assertIsNone(props["rejection_rate"])

    def test_a_single_perfect_run_is_still_insufficient(self) -> None:
        report = continuity_benchmark.summarize(benchmark_pack(), [benchmark_run()])
        self.assertEqual(report["overall"]["run_count"], 1)
        self.assertEqual(report["overall"]["sample_status"], "insufficient_sample")
        self.assertEqual(report["overall"]["first_pass_rate"], 1.0)
        self.assertIsNone(report["overall"]["mean_cost_usd"])
        self.assertEqual(report["evidence_tier"], "synthetic")

    def test_strata_separate_prompt_strategies(self) -> None:
        pack = benchmark_pack(minimum_sample_size=1)
        report = continuity_benchmark.summarize(
            pack,
            [benchmark_run(prompt_strategy="structured-state-v1"), benchmark_run(prompt_strategy="free-text")],
        )
        self.assertEqual(len(report["strata"]), 2)
        self.assertEqual(
            {row["prompt_strategy"] for row in report["strata"]},
            {"structured-state-v1", "free-text"},
        )

    def test_cli_writes_report_without_a_job_or_generation_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            pack_path = base / "pack.json"
            run_path = base / "run.json"
            out_path = base / "report.json"
            pack_path.write_text(json.dumps(benchmark_pack()), encoding="utf-8")
            run_path.write_text(json.dumps(benchmark_run()), encoding="utf-8")
            code, output = image_factory_cli.run_cli(
                [
                    "benchmark",
                    "--pack",
                    str(pack_path),
                    "--run",
                    str(run_path),
                    "--out",
                    str(out_path),
                    "--json",
                ]
            )
            self.assertEqual(code, 0, output)
            self.assertTrue(out_path.is_file())
            self.assertEqual(json.loads(out_path.read_text())["evidence_tier"], "synthetic")


class StructuredStoryStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def validate(self, plan: dict):
        return plan_validator.validate_plan(plan, base_dir=Path(self.tmp.name))

    def test_state_is_inherited_and_transitioned_deterministically(self) -> None:
        first = self.validate(story_plan())
        second = self.validate(story_plan())
        self.assertTrue(first.ok, first.errors)
        self.assertEqual(first.plan_sha256, second.plan_sha256)
        self.assertIn("character.student.hair = short black hair", first.items[0].effective_prompt)
        self.assertIn("prop.book.state = closed", first.items[0].effective_prompt)
        self.assertIn("prop.book.state = open", first.items[1].effective_prompt)
        self.assertIn("character.student.pose = seated", first.items[1].effective_prompt)
        self.assertNotEqual(first.items[0].idempotency_key, first.items[1].idempotency_key)

    def test_locked_path_cannot_also_be_variable(self) -> None:
        plan = story_plan()
        plan["consistency_profile"]["story_state"]["variables"].append(
            {"path": "character.student.age", "initial_value": "12"}
        )
        result = self.validate(plan)
        self.assertIn("plan_story_state_path_conflict", [error.code for error in result.errors])

    def test_transition_from_value_must_match_inherited_state(self) -> None:
        plan = story_plan()
        plan["items"][1]["state_transitions"][0]["from"] = "missing"
        result = self.validate(plan)
        self.assertIn("plan_story_state_transition_mismatch", [error.code for error in result.errors])

    def test_unknown_scene_fails_before_generation(self) -> None:
        plan = story_plan()
        plan["items"][0]["scene_id"] = "unknown-room"
        result = self.validate(plan)
        self.assertIn("plan_story_state_unknown_scene", [error.code for error in result.errors])

    def test_rework_keeps_state_inherited_from_a_passed_frame(self) -> None:
        plan = story_plan()
        plan["items"].append(
            {
                "id": "frame-03",
                "prompt": "学生继续阅读已经打开的书",
                "entity_ids": ["student"],
                "scene_id": "study-room",
            }
        )
        evaluation = {
            "deterministic_gates": {
                "per_item": [
                    {"item_id": "frame-01", "passed": True, "failures": []},
                    {"item_id": "frame-02", "passed": True, "failures": []},
                    {"item_id": "frame-03", "passed": False, "failures": ["not_a_png"]},
                ]
            },
            "human_labels": [],
            "advisory": {"items": []},
        }
        outcome = optimizer.plan_next_round(
            current_plan=plan,
            evaluation=evaluation,
            rewrites={"frame-03": "学生继续认真阅读已经打开的书"},
        )
        self.assertEqual([row["id"] for row in outcome.next_plan["items"]], ["frame-03"])
        next_result = self.validate(outcome.next_plan)
        self.assertTrue(next_result.ok, next_result.errors)
        self.assertIn("prop.book.state = open", next_result.items[0].effective_prompt)


class VersionedReviewerTests(unittest.TestCase):
    def test_missing_reviewer_version_is_rejected(self) -> None:
        report = reviewer_report()
        del report["reviewer"]["version"]
        with self.assertRaisesRegex(ValueError, "version"):
            reviewer_adapter.adapt(report)

    def test_low_confidence_finding_is_preserved_as_uncertain(self) -> None:
        adapted = reviewer_adapter.adapt(reviewer_report())
        self.assertEqual(adapted["reviewer"]["version"], "1.2.0")
        identity = adapted["items"][0]["findings"][0]
        self.assertTrue(identity["uncertain"])
        self.assertFalse(adapted["items"][0]["findings"][1]["uncertain"])
        self.assertEqual(adapted["authority"], "advisory")
        advisory = reviewer_adapter.merge_advisory([adapted])
        self.assertEqual(advisory["frame-01"]["score"], 0.9)
        self.assertEqual(advisory["frame-01"]["dimensions"][0]["name"], "wardrobe")

    def test_unknown_capability_is_rejected(self) -> None:
        report = reviewer_report()
        report["reviewer"]["capabilities"] = ["secret_superpower"]
        with self.assertRaisesRegex(ValueError, "capabilities"):
            reviewer_adapter.adapt(report)

    def test_reviewer_schema_uses_only_supported_keywords(self) -> None:
        schema = json.loads((ROOT / "schemas/reviewer_report.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema_lite.validate(reviewer_report(), schema), [])


if __name__ == "__main__":
    unittest.main()
