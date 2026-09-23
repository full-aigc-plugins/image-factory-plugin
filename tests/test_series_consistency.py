import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import artifact_collector  # noqa: E402
import generation_runner  # noqa: E402
import optimizer  # noqa: E402
import plan_validator  # noqa: E402


REAL_PNG = ROOT / "assets" / "logo.png"


class SeriesFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.character = self.base / "amu.png"
        self.style = self.base / "style.png"
        self.layout = self.base / "layout.png"
        self.character.write_bytes(b"character-anchor")
        self.style.write_bytes(b"style-anchor")
        self.layout.write_bytes(b"layout-anchor")

    def plan(self, **overrides) -> dict:
        document = {
            "schema_version": "1.3.0",
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
                "style_bible": "warm Chinese watercolor picture book, soft paper texture",
                "negative_constraints": ["no readable text", "do not change clothing colors"],
                "style_reference_images": [str(self.style)],
                "entities": [
                    {
                        "id": "amu",
                        "kind": "character",
                        "description": "a diligent young apprentice",
                        "fixed_traits": ["round face", "blue robe", "red cloth belt"],
                        "reference_images": [str(self.character)],
                    }
                ],
            },
            "items": [
                {
                    "id": "scene-01",
                    "prompt": "A Mu practices calligraphy at dawn.",
                    "entity_ids": ["amu"],
                    "allowed_variations": ["pose", "facial expression"],
                    "references": [
                        {"path": str(self.layout), "role": "layout"}
                    ],
                }
            ],
        }
        document.update(overrides)
        return document

    def validate(self, plan: dict | None = None) -> plan_validator.PlanResult:
        return plan_validator.validate_plan(plan or self.plan(), base_dir=self.base)

    def cleanup(self) -> None:
        self._tmp.cleanup()


class SeriesPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = SeriesFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_series_profile_compiles_effective_prompt_and_ordered_reference_roles(self) -> None:
        result = self.fixture.validate()
        self.assertTrue(result.ok, result.errors)
        item = result.items[0]
        self.assertIn("SERIES CONSISTENCY CONTRACT", item.effective_prompt)
        self.assertIn("warm Chinese watercolor picture book", item.effective_prompt)
        self.assertIn("round face; blue robe; red cloth belt", item.effective_prompt)
        self.assertIn("Allowed variations: pose; facial expression", item.effective_prompt)
        self.assertIn("SCENE REQUEST", item.effective_prompt)
        self.assertTrue(item.effective_prompt.endswith("A Mu practices calligraphy at dawn."))
        self.assertEqual(
            [(binding.role, binding.entity_id) for binding in item.reference_bindings],
            [("style", None), ("identity", "amu"), ("layout", None)],
        )
        self.assertEqual(item.reference_images, (str(self.fixture.style), str(self.fixture.character), str(self.fixture.layout)))
        self.assertEqual(
            item.effective_prompt_sha256,
            hashlib.sha256(item.effective_prompt.encode("utf-8")).hexdigest(),
        )
        self.assertRegex(result.consistency_profile_sha256 or "", r"^[0-9a-f]{64}$")

    def test_two_frames_share_identical_entity_contract(self) -> None:
        plan = self.fixture.plan()
        second = dict(plan["items"][0])
        second.update({"id": "scene-02", "prompt": "A Mu helps villagers in the rain."})
        plan["items"] = [plan["items"][0], second]
        result = self.fixture.validate(plan)
        self.assertTrue(result.ok, result.errors)
        first_contract = result.items[0].effective_prompt.split("[SCENE REQUEST]", 1)[0]
        second_contract = result.items[1].effective_prompt.split("[SCENE REQUEST]", 1)[0]
        self.assertEqual(first_contract, second_contract)

    def test_unknown_entity_is_rejected_before_generation(self) -> None:
        plan = self.fixture.plan()
        plan["items"][0]["entity_ids"] = ["teacher"]
        result = self.fixture.validate(plan)
        self.assertFalse(result.ok)
        self.assertIn("plan_unknown_entity", [error.code for error in result.errors])

    def test_effective_reference_limit_counts_profile_and_item_anchors(self) -> None:
        plan = self.fixture.plan()
        for index in range(3):
            target = self.fixture.base / f"extra-{index}.png"
            target.write_bytes(f"extra-{index}".encode())
            plan["items"][0]["references"].append({"path": str(target), "role": "generic"})
        # style + character + layout + three generic references = six
        result = self.fixture.validate(plan)
        self.assertFalse(result.ok)
        self.assertIn("plan_too_many_effective_references", [error.code for error in result.errors])

    def test_reference_role_is_part_of_generation_identity(self) -> None:
        first = self.fixture.validate()
        changed = self.fixture.plan()
        changed["items"][0]["references"][0]["role"] = "edit_target"
        second = self.fixture.validate(changed)
        self.assertTrue(first.ok and second.ok, (first.errors, second.errors))
        self.assertNotEqual(first.items[0].idempotency_key, second.items[0].idempotency_key)

    def test_fixed_trait_change_updates_plan_and_generation_identity(self) -> None:
        first = self.fixture.validate()
        changed = self.fixture.plan()
        changed["consistency_profile"]["entities"][0]["fixed_traits"][1] = "green robe"
        second = self.fixture.validate(changed)
        self.assertNotEqual(first.plan_sha256, second.plan_sha256)
        self.assertNotEqual(first.items[0].idempotency_key, second.items[0].idempotency_key)

    def test_legacy_1_2_plan_migrates_without_inventing_a_profile(self) -> None:
        legacy = self.fixture.plan()
        legacy["schema_version"] = "1.2.0"
        legacy.pop("consistency_profile")
        legacy["items"] = [{"id": "scene-01", "prompt": "plain scene"}]
        result = self.fixture.validate(legacy)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.items[0].effective_prompt, "plain scene")
        self.assertIsNone(result.consistency_profile_sha256)
        self.assertIn("migrated image batch 1.2.0 to 1.3.0", result.migration_notes)


class SeriesExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = SeriesFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_runner_uses_effective_prompt_instead_of_uncompiled_author_prompt(self) -> None:
        item = self.fixture.validate().items[0]
        argv = generation_runner.build_item_argv(
            binary="codex",
            item=item,
            workdir=self.fixture.base / "work",
            last_message_path=self.fixture.base / "last.txt",
        )
        self.assertEqual(argv[-1], generation_runner.build_prompt(item.effective_prompt))
        self.assertIn("SERIES CONSISTENCY CONTRACT", argv[-1])

    def test_receipt_hashes_the_effective_prompt(self) -> None:
        item = self.fixture.validate().items[0]
        generation_dir = self.fixture.base / "generated"
        destination = self.fixture.base / "out"
        source = generation_dir / "session-a" / "call-a.png"
        source.parent.mkdir(parents=True)
        destination.mkdir()
        before = artifact_collector.snapshot(generation_dir)
        shutil.copyfile(REAL_PNG, source)
        result = artifact_collector.collect_artifact(
            item=item,
            batch_id="diligence-story",
            generation_dir=generation_dir,
            destination_dir=destination,
            before=before,
            min_dimension=64,
        )
        self.assertTrue(result.ok, result.failure)
        self.assertEqual(result.receipt["prompt_sha256"], item.effective_prompt_sha256)

    def test_optimizer_retains_series_profile_and_item_bindings(self) -> None:
        current = self.fixture.plan()
        evaluation = {
            "deterministic_gates": {
                "per_item": [{"item_id": "scene-01", "passed": False, "failures": ["not_a_png"]}]
            },
            "human_labels": [],
            "advisory": {"items": []},
        }
        result = optimizer.plan_next_round(
            current_plan=current,
            evaluation=evaluation,
            rewrites={"scene-01": "A Mu practices again with steadier hands."},
        )
        self.assertEqual(result.next_plan["schema_version"], "1.6.0")
        self.assertEqual(result.next_plan["consistency_profile"], current["consistency_profile"])
        next_item = result.next_plan["items"][0]
        self.assertEqual(next_item["entity_ids"], ["amu"])
        self.assertEqual(next_item["allowed_variations"], ["pose", "facial expression"])
        self.assertEqual(next_item["references"], current["items"][0]["references"])


if __name__ == "__main__":
    unittest.main()
