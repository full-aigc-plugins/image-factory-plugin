import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import job_ledger  # noqa: E402
import plan_validator  # noqa: E402
import schema_lite  # noqa: E402


JOB_SCHEMA = json.loads((ROOT / "schemas/factory_job.schema.json").read_text(encoding="utf-8"))
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


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


class LedgerFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.path = self.base / "job.json"

    def ledger(self, job_id: str = "portrait-study") -> job_ledger.JobLedger:
        return job_ledger.JobLedger(self.path, job_id=job_id)

    def cleanup(self) -> None:
        self._tmp.cleanup()


class NewJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = LedgerFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_new_job_conforms_to_the_published_schema(self) -> None:
        payload = job_ledger.new_job("portrait-study")
        self.assertEqual(schema_lite.validate(payload, JOB_SCHEMA), [])

    def test_new_job_starts_as_an_unspent_draft(self) -> None:
        payload = job_ledger.new_job("portrait-study")
        self.assertEqual(payload["state"], "Draft")
        self.assertEqual(payload["revision"], 1)
        self.assertEqual(payload["history"], [])
        self.assertEqual(payload["items"], [])
        self.assertIsNone(payload["error_category"])
        self.assertIsNone(payload["usage_limit"])
        self.assertEqual(payload["approval"], {"current": None, "history": []})
        self.assertIsNone(payload["evaluation"])
        self.assertIsNone(payload["optimization"])
        self.assertRegex(payload["created_at"], ISO)

    def test_invalid_job_id_is_rejected(self) -> None:
        for bad in ("A", "ab", "has space", "UPPER", "x" * 65):
            with self.subTest(job_id=bad):
                with self.assertRaises(ValueError):
                    job_ledger.new_job(bad)


class TransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = LedgerFixture()
        self.addCleanup(self.fixture.cleanup)
        self.ledger = self.fixture.ledger()
        self.ledger.write(job_ledger.new_job("portrait-study"))

    def test_forward_transition_is_recorded(self) -> None:
        payload = self.ledger.transition(job_ledger.JobState.PLAN_VALIDATED)
        self.assertEqual(payload["state"], "PlanValidated")
        self.assertEqual(payload["revision"], 2)
        self.assertEqual(len(payload["history"]), 1)
        entry = payload["history"][0]
        self.assertEqual(entry["from_state"], "Draft")
        self.assertEqual(entry["to_state"], "PlanValidated")
        self.assertRegex(entry["at"], ISO)
        self.assertRegex(payload["updated_at"], ISO)

    def test_illegal_transition_is_rejected(self) -> None:
        with self.assertRaises(job_ledger.InvalidTransitionError):
            self.ledger.transition(job_ledger.JobState.COMPLETED)

    def test_revision_increases_monotonically(self) -> None:
        revisions = [self.ledger.read()["revision"]]
        for state in (
            job_ledger.JobState.PLAN_VALIDATED,
            job_ledger.JobState.APPROVED,
            job_ledger.JobState.RUNNING,
            job_ledger.JobState.COMPLETED,
        ):
            revisions.append(self.ledger.transition(state)["revision"])
        self.assertEqual(revisions, sorted(revisions))
        self.assertEqual(revisions, [1, 2, 3, 4, 5])

    def test_running_cannot_be_entered_without_approval(self) -> None:
        """1.1.0 makes approval an unavoidable step, so Running is not a shortcut."""
        self.ledger.transition(job_ledger.JobState.PLAN_VALIDATED)
        with self.assertRaises(job_ledger.InvalidTransitionError):
            self.ledger.transition(job_ledger.JobState.RUNNING)

    def test_failed_is_terminal(self) -> None:
        self.ledger.transition(job_ledger.JobState.FAILED)
        with self.assertRaises(job_ledger.InvalidTransitionError):
            self.ledger.transition(job_ledger.JobState.PLAN_VALIDATED)

    def test_unknown_state_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.ledger.transition("NotAState")

    def test_every_declared_state_is_reachable_in_the_transition_table(self) -> None:
        states = {state.value for state in job_ledger.JobState}
        reachable = {job_ledger.JobState.DRAFT.value}
        for targets in job_ledger.ALLOWED_TRANSITIONS.values():
            reachable.update(target.value for target in targets)
        self.assertEqual(states, reachable)

    def test_history_records_a_note_when_given(self) -> None:
        payload = self.ledger.transition(job_ledger.JobState.FAILED, note="plan rejected")
        self.assertEqual(payload["history"][0]["note"], "plan rejected")


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = LedgerFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_write_is_atomic_and_leaves_no_temporary_files(self) -> None:
        ledger = self.fixture.ledger()
        ledger.write(job_ledger.new_job("portrait-study"))
        leftovers = [entry.name for entry in self.fixture.base.iterdir() if entry.name != "job.json"]
        self.assertEqual(leftovers, [])
        self.assertTrue(self.fixture.path.is_file())

    def test_written_ledger_validates_against_the_schema(self) -> None:
        ledger = self.fixture.ledger()
        ledger.write(job_ledger.new_job("portrait-study"))
        ledger.transition(job_ledger.JobState.PLAN_VALIDATED)
        payload = ledger.transition(job_ledger.JobState.APPROVED)
        self.assertEqual(schema_lite.validate(payload, JOB_SCHEMA), [])

    def test_secret_keys_are_refused_on_write(self) -> None:
        ledger = self.fixture.ledger()
        payload = job_ledger.new_job("portrait-study")
        payload["batch"] = {"api_key": "should-never-be-stored"}
        before = self.fixture.path.read_bytes() if self.fixture.path.exists() else b""
        with self.assertRaises(job_ledger.LedgerCorruptError):
            ledger.write(payload)
        after = self.fixture.path.read_bytes() if self.fixture.path.exists() else b""
        self.assertEqual(before, after)

    def test_secret_keys_are_refused_on_load(self) -> None:
        payload = job_ledger.new_job("portrait-study")
        payload["approval"] = {"authorization": "x", "nested": [{"password": "hunter2"}]}
        self.fixture.path.write_text(json.dumps(payload), encoding="utf-8")
        ledger = self.fixture.ledger()
        with self.assertRaises(job_ledger.LedgerCorruptError):
            ledger.read()

    def test_corrupt_json_is_refused(self) -> None:
        self.fixture.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(job_ledger.LedgerCorruptError):
            self.fixture.ledger().read()

    def test_missing_required_fields_are_refused(self) -> None:
        self.fixture.path.write_text(json.dumps({"schema_version": "1.0.0"}), encoding="utf-8")
        with self.assertRaises(job_ledger.LedgerCorruptError):
            self.fixture.ledger().read()

    def test_unsupported_schema_version_is_refused(self) -> None:
        payload = job_ledger.new_job("portrait-study")
        payload["schema_version"] = "2.0.0"
        self.fixture.path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(job_ledger.LedgerCorruptError):
            self.fixture.ledger().read()

    def test_missing_ledger_is_reported_clearly(self) -> None:
        with self.assertRaises(job_ledger.LedgerCorruptError):
            self.fixture.ledger().read()

    def test_secret_scan_is_case_insensitive(self) -> None:
        payload = job_ledger.new_job("portrait-study")
        payload["batch"] = {"API_KEY": "x"}
        with self.assertRaises(job_ledger.LedgerCorruptError):
            self.fixture.ledger().write(payload)


class ItemTrackingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = LedgerFixture()
        self.addCleanup(self.fixture.cleanup)
        self.ledger = self.fixture.ledger()
        self.ledger.write(job_ledger.new_job("portrait-study"))
        self.items = (make_item("item-01"), make_item("item-02"))

    def test_fresh_job_has_every_item_pending(self) -> None:
        pending = self.ledger.pending_items(self.items)
        self.assertEqual([item.id for item in pending], ["item-01", "item-02"])

    def test_generated_item_is_not_pending_again(self) -> None:
        """The whole point of the idempotency key: a resume must not pay twice."""
        self.ledger.record_item(self.items[0], state="Generated", receipt_id="rec-1")
        pending = self.ledger.pending_items(self.items)
        self.assertEqual([item.id for item in pending], ["item-02"])

    def test_failed_item_is_not_retried_automatically(self) -> None:
        self.ledger.record_item(self.items[0], state="Failed", error_category="timeout")
        pending = self.ledger.pending_items(self.items)
        self.assertEqual([item.id for item in pending], ["item-02"])

    def test_attempts_are_counted(self) -> None:
        payload = self.ledger.record_item(self.items[0], state="Failed", error_category="generation_failed")
        self.assertEqual(payload["items"][0]["attempts"], 1)
        payload = self.ledger.record_item(self.items[0], state="Generated", receipt_id="rec-1")
        self.assertEqual(payload["items"][0]["attempts"], 2)

    def test_receipt_and_key_are_recorded(self) -> None:
        payload = self.ledger.record_item(self.items[0], state="Generated", receipt_id="rec-1")
        entry = payload["items"][0]
        self.assertEqual(entry["receipt_id"], "rec-1")
        self.assertEqual(entry["idempotency_key"], self.items[0].idempotency_key)
        self.assertIsNone(entry["error_category"])

    def test_ledger_with_items_validates_against_the_schema(self) -> None:
        payload = self.ledger.record_item(self.items[0], state="Generated", receipt_id="rec-1")
        self.assertEqual(schema_lite.validate(payload, JOB_SCHEMA), [])

    def test_unknown_item_state_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.ledger.record_item(self.items[0], state="Whatever")

    def test_marking_an_item_pending_is_not_counted_as_an_attempt(self) -> None:
        payload = self.ledger.record_item(self.items[0], state="Pending")
        self.assertEqual(payload["items"][0]["attempts"], 0)


class UsageLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = LedgerFixture()
        self.addCleanup(self.fixture.cleanup)
        self.ledger = self.fixture.ledger()
        self.ledger.write(job_ledger.new_job("portrait-study"))

    def test_usage_limit_is_recorded_with_its_reset_time(self) -> None:
        payload = self.ledger.note_usage_limit(limit_id="image_gen", resets_at=1_800_000_000)
        self.assertEqual(payload["usage_limit"], {"limit_id": "image_gen", "resets_at": 1_800_000_000})
        self.assertEqual(payload["error_category"], "quota_exceeded")

    def test_usage_limit_without_reset_time_is_still_recorded(self) -> None:
        payload = self.ledger.note_usage_limit(limit_id="image_gen", resets_at=None)
        self.assertIsNone(payload["usage_limit"]["resets_at"])

    def test_only_the_image_limit_is_accepted(self) -> None:
        with self.assertRaises(ValueError):
            self.ledger.note_usage_limit(limit_id="something_else", resets_at=None)

    def test_usage_limit_payload_validates_against_the_schema(self) -> None:
        payload = self.ledger.note_usage_limit(limit_id="image_gen", resets_at=None)
        self.assertEqual(schema_lite.validate(payload, JOB_SCHEMA), [])

    def test_error_category_round_trips_through_the_schema(self) -> None:
        for category in job_ledger.ERROR_CATEGORIES:
            with self.subTest(category=category):
                payload = job_ledger.new_job("portrait-study")
                payload["error_category"] = category
                self.assertEqual(schema_lite.validate(payload, JOB_SCHEMA), [], category)


class ApprovalBindingTests(unittest.TestCase):
    """An approval authorizes one plan, one round, and one call count — nothing else."""

    def setUp(self) -> None:
        self.fixture = LedgerFixture()
        self.addCleanup(self.fixture.cleanup)
        self.ledger = self.fixture.ledger()
        self.ledger.write(job_ledger.new_job("portrait-study"))

    def test_approval_is_bound_to_exact_plan_and_count(self) -> None:
        self.ledger.record_approval("a" * 64, 1, 2, "run_approve_flag")
        self.assertTrue(self.ledger.approval_matches("a" * 64, 1, 2))
        self.assertFalse(self.ledger.approval_matches("b" * 64, 1, 2))
        self.assertFalse(self.ledger.approval_matches("a" * 64, 1, 1))
        self.assertFalse(self.ledger.approval_matches("a" * 64, 2, 2))

    def test_a_job_without_approval_matches_nothing(self) -> None:
        self.assertFalse(self.ledger.approval_matches("a" * 64, 1, 2))

    def test_only_a_provable_source_is_accepted(self) -> None:
        with self.assertRaises(ValueError):
            self.ledger.record_approval("a" * 64, 1, 2, "trust_me")

    def test_approval_history_accumulates_and_current_follows(self) -> None:
        self.ledger.record_approval("a" * 64, 1, 2, "run_approve_flag")
        payload = self.ledger.record_approval("b" * 64, 2, 1, "run_approve_flag")
        self.assertEqual(len(payload["approval"]["history"]), 2)
        self.assertEqual(payload["approval"]["current"]["plan_hash"], "b" * 64)

    def test_binding_a_different_plan_clears_current_and_keeps_history(self) -> None:
        self.ledger.record_approval("a" * 64, 1, 2, "run_approve_flag")
        payload = self.ledger.bind_plan("b" * 64, 2, 1)
        self.assertIsNone(payload["approval"]["current"])
        self.assertEqual(len(payload["approval"]["history"]), 1)
        self.assertFalse(self.ledger.approval_matches("a" * 64, 1, 2))

    def test_binding_the_same_plan_keeps_the_approval(self) -> None:
        self.ledger.record_approval("a" * 64, 1, 2, "run_approve_flag")
        payload = self.ledger.bind_plan("a" * 64, 1, 2)
        self.assertTrue(self.ledger.approval_matches("a" * 64, 1, 2))
        self.assertEqual(payload["batch"]["image_count"], 2)

    def test_binding_stores_only_identity_and_count(self) -> None:
        payload = self.ledger.bind_plan("a" * 64, 1, 2)
        self.assertEqual(
            sorted(payload["batch"]),
            ["batch_id", "image_count", "plan_hash", "round"],
        )
        self.assertEqual(payload["batch"]["batch_id"], payload["job_id"])

    def test_a_bound_ledger_validates_against_the_schema(self) -> None:
        self.ledger.bind_plan("a" * 64, 1, 2)
        self.ledger.record_approval("a" * 64, 1, 2, "run_approve_flag")
        payload = self.ledger.read()
        self.assertEqual(schema_lite.validate(payload, JOB_SCHEMA), [])


class AttemptLifecycleTests(unittest.TestCase):
    """An attempt is a fact about a call that may have happened, so it is counted once."""

    def setUp(self) -> None:
        self.fixture = LedgerFixture()
        self.addCleanup(self.fixture.cleanup)
        self.ledger = self.fixture.ledger()
        self.ledger.write(job_ledger.new_job("portrait-study"))
        self.item = make_item("item-01")

    def test_attempt_is_counted_once_when_it_starts(self) -> None:
        started = self.ledger.start_attempt(self.item, "attempt-1")
        completed = self.ledger.complete_attempt(self.item, "attempt-1", "receipt-1")
        self.assertEqual(started["items"][0]["attempts"], 1)
        self.assertEqual(completed["items"][0]["attempts"], 1)

    def test_starting_records_the_attempt_identity_and_time(self) -> None:
        payload = self.ledger.start_attempt(self.item, "attempt-1")
        entry = payload["items"][0]
        self.assertEqual(entry["state"], "Attempting")
        self.assertEqual(entry["attempt_id"], "attempt-1")
        self.assertRegex(entry["attempt_started_at"], ISO)

    def test_unknown_attempt_is_never_pending(self) -> None:
        self.ledger.start_attempt(self.item, "attempt-1")
        self.ledger.mark_attempt_unknown(self.item.id, "attempt-1")
        self.assertEqual(self.ledger.pending_items((self.item,)), [])

    def test_an_interrupted_item_is_never_started_again(self) -> None:
        self.ledger.start_attempt(self.item, "attempt-1")
        with self.assertRaises(job_ledger.InvalidTransitionError):
            self.ledger.start_attempt(self.item, "attempt-2")

    def test_a_generated_item_is_never_started_again(self) -> None:
        self.ledger.start_attempt(self.item, "attempt-1")
        self.ledger.complete_attempt(self.item, "attempt-1", "receipt-1")
        with self.assertRaises(job_ledger.InvalidTransitionError):
            self.ledger.start_attempt(self.item, "attempt-2")

    def test_completing_with_a_stale_attempt_id_is_refused(self) -> None:
        self.ledger.start_attempt(self.item, "attempt-1")
        with self.assertRaises(job_ledger.InvalidTransitionError):
            self.ledger.complete_attempt(self.item, "attempt-2", "receipt-1")

    def test_failing_records_the_error_category(self) -> None:
        self.ledger.start_attempt(self.item, "attempt-1")
        payload = self.ledger.fail_attempt(self.item, "attempt-1", "timeout")
        entry = payload["items"][0]
        self.assertEqual(entry["state"], "Failed")
        self.assertEqual(entry["error_category"], "timeout")
        self.assertEqual(entry["attempts"], 1)

    def test_failing_with_a_stale_attempt_id_is_refused(self) -> None:
        self.ledger.start_attempt(self.item, "attempt-1")
        with self.assertRaises(job_ledger.InvalidTransitionError):
            self.ledger.fail_attempt(self.item, "attempt-2", "timeout")

    def test_completing_requires_a_receipt_id(self) -> None:
        self.ledger.start_attempt(self.item, "attempt-1")
        with self.assertRaises(ValueError):
            self.ledger.complete_attempt(self.item, "attempt-1", "")

    def test_an_unknown_category_is_refused(self) -> None:
        self.ledger.start_attempt(self.item, "attempt-1")
        with self.assertRaises(ValueError):
            self.ledger.fail_attempt(self.item, "attempt-1", "not_a_category")

    def test_a_lifecycle_ledger_validates_against_the_schema(self) -> None:
        self.ledger.start_attempt(self.item, "attempt-1")
        self.ledger.mark_attempt_unknown(self.item.id, "attempt-1")
        self.assertEqual(schema_lite.validate(self.ledger.read(), JOB_SCHEMA), [])


class StateMachineSafetyTests(unittest.TestCase):
    """No transition may return a settled job to spending without a fresh approval."""

    def setUp(self) -> None:
        self.fixture = LedgerFixture()
        self.addCleanup(self.fixture.cleanup)

    def locked(self, state: str) -> job_ledger.JobLedger:
        ledger = self.fixture.ledger()
        payload = job_ledger.new_job("portrait-study")
        payload["state"] = state
        ledger.write(payload)
        return ledger

    def test_settled_states_cannot_return_to_running(self) -> None:
        for state in ("PlanValidated", "Unknown", "Completed"):
            with self.subTest(state=state):
                ledger = self.locked(state)
                with self.assertRaises(job_ledger.InvalidTransitionError):
                    ledger.transition(job_ledger.JobState.RUNNING)

    def test_evaluated_may_move_to_the_next_cycle(self) -> None:
        for target in ("PendingApproval", "Accepted", "Optimized"):
            with self.subTest(target=target):
                ledger = self.locked("Evaluated")
                payload = ledger.transition(target)
                self.assertEqual(payload["state"], target)

    def test_accepted_and_failed_are_terminal(self) -> None:
        for state in ("Accepted", "Failed"):
            with self.subTest(state=state):
                ledger = self.locked(state)
                for target in ("Running", "PlanValidated", "PendingApproval", "Approved"):
                    with self.subTest(state=state, target=target):
                        with self.assertRaises(job_ledger.InvalidTransitionError):
                            ledger.transition(target)

    def test_running_is_reachable_only_through_approval(self) -> None:
        ledger = self.locked("PlanValidated")
        ledger.transition(job_ledger.JobState.PENDING_APPROVAL)
        ledger.transition(job_ledger.JobState.APPROVED)
        self.assertEqual(ledger.transition(job_ledger.JobState.RUNNING)["state"], "Running")


if __name__ == "__main__":
    unittest.main()
