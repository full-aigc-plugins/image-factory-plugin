import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
sys.path.insert(0, str(ROOT / "scripts"))

import job_ledger  # noqa: E402

EXPECTED = (
    "codex-image-factory-use",
    "codex-image-factory-run",
    "codex-image-factory-judge",
    "codex-image-factory-recover",
)
ROUTER = "codex-image-factory-use"
DELEGATES = tuple(name for name in EXPECTED if name != ROUTER)

# The CLI subcommand each workflow skill is responsible for driving.
COMMANDS = {
    "codex-image-factory-run": "run",
    "codex-image-factory-judge": "evaluate",
    "codex-image-factory-recover": "status",
}

FORBIDDEN_PHRASES = (
    "pip install",
    "brew install",
    "apt-get install",
    "npm install",
    "silently install",
    "auto-retry",
    "auto retry",
    "automatically retry",
    "automatic retry",
    "retry automatically",
)


def parse_frontmatter(text: str) -> dict:
    """Parse frontmatter the way the consumer does, not the way YAML allows.

    The Skill loader takes everything after the first colon on a line as the
    value, so it has no notion of YAML block scalars: `description: >` yields the
    single character `>`. An earlier version of this helper understood block
    scalars, which made it more permissive than production and therefore unable
    to prove anything. It now matches the consumer exactly.
    """
    if not text.startswith("---\n"):
        raise AssertionError("SKILL.md must start with a frontmatter block")
    end = text.index("\n---", 4)
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.startswith((" ", "\t")):
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip("'\"")
    return fields


class SkillInventoryTests(unittest.TestCase):
    def test_exactly_the_expected_skills_exist(self) -> None:
        present = tuple(sorted(entry.name for entry in SKILLS.iterdir() if entry.is_dir()))
        self.assertEqual(present, tuple(sorted(EXPECTED)))

    def test_every_skill_is_a_directory_with_a_manifest(self) -> None:
        for name in EXPECTED:
            with self.subTest(skill=name):
                self.assertTrue((SKILLS / name / "SKILL.md").is_file(), name)

    def test_skills_do_not_ship_helper_documents(self) -> None:
        """Agent Skills forbid README-style companions that silently inflate context."""
        for name in EXPECTED:
            for entry in (SKILLS / name).iterdir():
                with self.subTest(skill=name, entry=entry.name):
                    self.assertIn(entry.name, ("SKILL.md", "references", "scripts", "assets"))


class FrontmatterTests(unittest.TestCase):
    def test_name_matches_the_directory(self) -> None:
        for name in EXPECTED:
            with self.subTest(skill=name):
                fields = parse_frontmatter((SKILLS / name / "SKILL.md").read_text(encoding="utf-8"))
                self.assertEqual(fields.get("name"), name)

    def test_description_is_within_limits(self) -> None:
        for name in EXPECTED:
            with self.subTest(skill=name):
                fields = parse_frontmatter((SKILLS / name / "SKILL.md").read_text(encoding="utf-8"))
                description = fields.get("description", "")
                self.assertGreater(len(description), 32)
                self.assertLessEqual(len(description), 1024)

    def test_description_is_a_single_line_value(self) -> None:
        """A YAML block scalar parses as one character and the Skill then never triggers."""
        for name in EXPECTED:
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            head = text[4 : text.index("\n---", 4)]
            with self.subTest(skill=name):
                match = re.search(r"^description:(.*)$", head, re.MULTILINE)
                self.assertIsNotNone(match, f"{name}: no description line")
                value = match.group(1).strip()
                self.assertNotIn(
                    value, ("|", ">", "|-", ">-", "|+", ">+"), "block scalars are not read by the loader"
                )
                self.assertGreater(len(value), 32)

    def test_description_is_a_valid_yaml_plain_scalar(self) -> None:
        """A colon-space or a space-hash inside a plain scalar makes the frontmatter invalid YAML.

        Both parsers matter and they pull in opposite directions: the Skill loader
        splits on the first colon and cannot read a block scalar, while the plugin
        validator parses the frontmatter as real YAML and rejects a plain scalar
        containing `": "`. A single line without those sequences satisfies both.
        """
        for name in EXPECTED:
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            head = text[4 : text.index("\n---", 4)]
            match = re.search(r"^description:(.*)$", head, re.MULTILINE)
            assert match is not None
            value = match.group(1).strip()
            with self.subTest(skill=name):
                self.assertNotIn(": ", value, "a colon-space breaks YAML plain scalars")
                self.assertNotIn(" #", value, "a space-hash starts a YAML comment")
                self.assertTrue(value.endswith(".") or value.endswith("`"))

    def test_description_states_when_to_use_the_skill(self) -> None:
        for name in EXPECTED:
            with self.subTest(skill=name):
                fields = parse_frontmatter((SKILLS / name / "SKILL.md").read_text(encoding="utf-8"))
                self.assertIn("Use when", fields.get("description", ""))

    def test_router_description_names_every_delegate(self) -> None:
        fields = parse_frontmatter((SKILLS / ROUTER / "SKILL.md").read_text(encoding="utf-8"))
        description = fields.get("description", "")
        for delegate in DELEGATES:
            with self.subTest(delegate=delegate):
                self.assertIn(delegate, description)

    def test_workflow_descriptions_are_distinguishable(self) -> None:
        seen: dict[str, str] = {}
        for name in DELEGATES:
            fields = parse_frontmatter((SKILLS / name / "SKILL.md").read_text(encoding="utf-8"))
            seen[name] = fields.get("description", "")
        self.assertEqual(len(set(seen.values())), len(seen))


class BodyTests(unittest.TestCase):
    def body(self, name: str) -> str:
        text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        return text[text.index("\n---", 4) + 4 :]

    def test_every_skill_has_the_required_sections(self) -> None:
        for name in EXPECTED:
            with self.subTest(skill=name):
                body = self.body(name)
                self.assertIn("## When to use", body)
                self.assertIn("## Workflow", body)
                self.assertIn("## Never do", body)

    def test_workflow_skills_name_the_cli_command_they_drive(self) -> None:
        for name, command in COMMANDS.items():
            with self.subTest(skill=name):
                self.assertIn(f"bin/image-factory {command}", self.body(name))

    def test_workflow_skills_say_validate(self) -> None:
        for name in DELEGATES:
            with self.subTest(skill=name):
                self.assertIn("validate", self.body(name).lower())

    def test_router_does_not_duplicate_workflow_detail(self) -> None:
        body = self.body(ROUTER)
        self.assertNotIn("## Implementation", body)

    def test_run_skill_requires_explicit_approval(self) -> None:
        body = self.body("codex-image-factory-run").lower()
        self.assertIn("approv", body)
        self.assertIn("never retries", body)

    def test_run_skill_forbids_bypassing_approvals(self) -> None:
        """Naming the bypass flag as forbidden is the point; using it is what must never happen."""
        body = self.body("codex-image-factory-run").lower()
        self.assertIn("never bypass approvals", body)
        self.assertIn("dangerously-bypass-approvals-and-sandbox", body)

    def test_judge_skill_treats_the_model_score_as_advisory(self) -> None:
        body = self.body("codex-image-factory-judge")
        self.assertIn("advisory", body.lower())
        self.assertIn("deterministic", body.lower())

    def test_judge_skill_keeps_the_human_in_the_loop(self) -> None:
        body = self.body("codex-image-factory-judge").lower()
        self.assertIn("approve", body)
        self.assertIn("reject", body)

    def test_judge_skill_distinguishes_definite_failure_from_unknown(self) -> None:
        body = self.body("codex-image-factory-judge").lower()
        self.assertIn("failed` and `skipped", body)
        self.assertIn("missing_artifact", body)
        self.assertIn("unknown", body)
        self.assertIn("explicit rewrite", body)
        self.assertIn("retry-unchanged", body)

    def test_recover_skill_routes_terminal_partial_items_to_evaluation(self) -> None:
        body = self.body("codex-image-factory-recover").lower()
        self.assertIn("no pending", body)
        self.assertIn("definite failures", body)
        self.assertIn("evaluate", body)
        self.assertIn("explicit rewrite", body)

    def test_recover_skill_requires_the_full_optimized_approval_sequence(self) -> None:
        body = self.body("codex-image-factory-recover").lower()
        optimized_row = next(
            line for line in body.splitlines() if line.strip().startswith("| `optimized`")
        )
        markers = (
            "validate the next plan",
            "quote the exact remaining generation calls",
            "obtain fresh approval",
            "run",
            "evaluate",
        )
        positions = [optimized_row.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))

    def test_recover_skill_maps_every_ledger_state(self) -> None:
        body = self.body("codex-image-factory-recover")
        for state in job_ledger.JobState:
            with self.subTest(state=state):
                self.assertIn(f"`{state.value}`", body)

    def test_run_skill_never_treats_stale_approval_as_permission_to_proceed(self) -> None:
        body = self.body("codex-image-factory-run")
        self.assertNotIn("already approved plan", body.lower())
        self.assertIn("verify", body.lower())
        self.assertIn("displayed plan", body.lower())
        self.assertIn("remaining generation-call", body.lower())

    def test_recover_skill_reconciles_before_recommending_a_next_action(self) -> None:
        body = self.body("codex-image-factory-recover").lower()
        self.assertIn("bin/image-factory recover", body)
        self.assertIn("completed", body)
        self.assertIn("failed", body)
        self.assertIn("pending", body)
        self.assertIn("unknown", body)
        self.assertNotIn("resume with `run`", body)
        self.assertIn("running`, `unknown`, `partial`, or `completed`", body)
        self.assertIn("do not call `recover`", body)

    def test_run_skill_requires_a_fresh_approval_for_partial_resume(self) -> None:
        body = self.body("codex-image-factory-run").lower()
        self.assertIn("remaining generation", body)
        self.assertIn("fresh approval", body)

    def test_all_skills_apply_the_transactional_conversation_contract(self) -> None:
        required = {
            "codex-image-factory-use": ("displayed plan", "round", "remaining generation-call"),
            "codex-image-factory-run": ("exact plan", "round", "remaining generation-call"),
            "codex-image-factory-judge": ("PendingApproval", "Accepted", "new approval"),
            "codex-image-factory-recover": ("Unknown", "zero generation calls", "do not re-run"),
        }
        for name, phrases in required.items():
            body = self.body(name)
            for phrase in phrases:
                with self.subTest(skill=name, phrase=phrase):
                    self.assertIn(phrase.lower(), body.lower())

    def test_no_skill_instructs_an_install_or_a_retry(self) -> None:
        for name in EXPECTED:
            body = self.body(name).lower()
            for phrase in FORBIDDEN_PHRASES:
                with self.subTest(skill=name, phrase=phrase):
                    self.assertNotIn(phrase, body)

    def test_no_skill_hardcodes_an_image_model(self) -> None:
        """The plugin must not promise a model the platform selects."""
        for name in EXPECTED:
            body = self.body(name).lower()
            for model in ("gpt-image", "image-2.5", "sunburst", "flare"):
                with self.subTest(skill=name, model=model):
                    self.assertNotIn(model, body)

    def test_bodies_declare_the_platform_boundary(self) -> None:
        """Each workflow skill must state that size and quality are not controllable."""
        for name in DELEGATES:
            with self.subTest(skill=name):
                body = self.body(name).lower()
                self.assertTrue(
                    "size" in body or "quality" in body,
                    "the skill must not imply it can control generation parameters",
                )


class MarkdownHygieneTests(unittest.TestCase):
    def test_headings_are_well_formed(self) -> None:
        for name in EXPECTED:
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=name):
                self.assertEqual(text.count("\n# "), 1, "exactly one H1")
                self.assertTrue(re.search(r"^# \S", text, re.MULTILINE))
                self.assertEqual(text.count("```") % 2, 0, "code fences must be balanced")


if __name__ == "__main__":
    unittest.main()
