# Codex Image Factory 0.1.2 Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every allowance-spending image generation call approval-bound, cross-process serialized, crash-recoverable, human-confirmed, and reproducibly releasable as Codex Image Factory 0.1.2.

**Architecture:** Keep the Codex conversation as the only product surface and retain the deterministic Python CLI as the execution boundary. Bind each approval to a validated plan hash, reserve each item before the external call, persist one atomic receipt per completed item, derive the aggregate manifest from those receipts, and refuse automatic retry whenever an interruption leaves external execution ambiguous.

**Tech Stack:** Python 3.11+ standard library, `unittest`, closed JSON Schema enforced by `scripts/schema_lite.py`, OS file locks through `fcntl`/`msvcrt`, Codex plugin manifest, Agent Skills, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-14-codex-image-factory-production-hardening-design.md`

## Global Constraints

- Preserve all existing uncommitted user changes; do not restore, delete, or overwrite unrelated files.
- Do not create or switch a Git branch unless the user explicitly authorizes it.
- Keep exactly four active Skills: `codex-image-factory-{use,run,judge,recover}`.
- The conversation remains the product surface; add no separate graphical interface.
- Keep this repository image-only; do not add video generation, editing, composition, or publication.
- Use the built-in Codex image capability and existing account authentication only.
- Add no external generation API, API key, automatic retry, or third-party Python dependency.
- Continue invoking Codex with an argv array and `shell=False`; never pass an approval- or sandbox-bypass flag.
- Every generation round requires fresh approval bound to the validated plan hash, round, and remaining call count.
- Never automatically retry an `Attempting` or `Unknown` item.
- Keep size, quality, background, output count, and model selection outside the image plan.
- Keep persisted schemas closed with `additionalProperties: false` and reject unsupported schema keywords.
- Preserve historical 1.0.0 plans and ledgers through deterministic, safety-strengthening migration.
- Run focused tests after each implementation step and the full suite before every task commit.
- Do not edit the installed plugin cache during implementation; validate it only through a fresh authorized reinstall after release.
- Require a paid canary on the released commit before declaring production readiness; record `NOT_RUN` and retain release-candidate status when authorization is absent.

---

## File Responsibility Map

| File | Responsibility after this change |
| --- | --- |
| `scripts/contract_migrations.py` | Upgrade image plans and job ledgers from schema 1.0.0 to 1.1.0 without weakening approval policy |
| `scripts/atomic_json.py` | Reusable same-directory temporary write, flush, fsync, and atomic replace for JSON evidence |
| `scripts/job_lock.py` | Cross-platform, process-scoped exclusive job mutation lock |
| `scripts/receipt_store.py` | Atomic per-item receipt storage, receipt verification, reconciliation, and manifest rebuilding |
| `scripts/plan_validator.py` | Schema-backed validation, reference hashing, human-label propagation, and canonical plan hashing |
| `scripts/job_ledger.py` | Versioned state machine, approval history, attempt lifecycle, evaluation/optimization evidence, and migration-aware persistence |
| `scripts/image_factory_cli.py` | Approval gate, locking, transaction ordering, recovery, state changes, and status reporting |
| `tests/fakes/fake_codex.py` | Deterministic invocation evidence, delay control, and crash/concurrency test support |
| `schemas/image_batch.schema.json` | Mandatory per-round approval and human result labels for plan 1.1.0 |
| `schemas/factory_job.schema.json` | Closed job 1.1.0 transaction, approval, attempt, evaluation, and optimization contract |
| `.github/workflows/ci.yml` | Linux/macOS/Windows regression gates |
| Four active `skills/*/SKILL.md` files | Natural-language confirmation, status, recovery, and result-label behavior |

### Task 0: Protect the dirty worktree and establish change ownership

**Files:**
- Inspect only: every path reported by `git status --short`
- Create during later tasks only: files explicitly listed by those tasks

**Interfaces:**
- Produces: a reviewed path inventory separating pre-existing conversation/documentation work from production-hardening work
- Constrains: every later `git add` to explicit paths

- [x] **Step 1: Capture the read-only repository baseline**

```bash
git branch --show-current
git status --short
git diff --name-status
git diff --check
git rev-parse HEAD
git rev-parse @{upstream}
```

Expected: branch and revisions are recorded; existing modified, deleted, and
untracked paths remain untouched.

- [x] **Step 2: Inspect overlap with planned files**

```bash
git diff -- skills docs README.md README.zh-CN.md CHANGELOG.md
git diff -- scripts schemas tests .codex-plugin .github
```

Expected: the first command shows pre-existing conversational/documentation work;
the second confirms whether any runtime path already has user changes. Do not
discard either group.

- [x] **Step 3: Establish selective-staging discipline**

Before every later commit:

```bash
git diff --cached --name-status
git diff --cached --check
```

Expected: only the task's listed files are staged. If a planned file already
contains user-authored changes, preserve them and review the combined diff.

### Task 1: Freeze the 1.1.0 contracts and migration boundary

**Files:**
- Create: `scripts/contract_migrations.py`
- Create: `tests/test_contract_migrations.py`
- Modify: `schemas/image_batch.schema.json:8-59`
- Modify: `schemas/factory_job.schema.json:8-98`
- Modify: `scripts/plan_validator.py:25-33,148-260`
- Modify: `scripts/job_ledger.py:28-34,129-199`
- Modify: `tests/test_contracts.py:79-207`
- Modify: `tests/test_plan.py:1-180`
- Modify: `tests/test_ledger.py:51-201`

**Interfaces:**
- Produces: `MigrationResult(document: dict, notes: tuple[str, ...])`
- Produces: `migrate_image_batch(document: object) -> MigrationResult`
- Produces: `migrate_factory_job(document: object) -> MigrationResult`
- Consumed later by: `plan_validator.validate_plan` and `job_ledger.load_ledger`

- [x] **Step 1: Write failing image-plan contract tests**

Add `load_schema(name: str) -> dict` at module scope; it loads the named file
from `schemas/` with UTF-8 and `json.loads`. Then add:

```python
def test_image_plan_1_1_requires_both_human_gates(self) -> None:
    schema = load_schema("image_batch.schema.json")
    self.assertEqual(schema["properties"]["schema_version"]["const"], "1.1.0")
    limits = schema["$defs"]["batchLimits"]
    policy = schema["$defs"]["judgePolicy"]
    self.assertEqual(limits["properties"]["require_approval_before_run"], {"const": True})
    self.assertIn("require_human_labels", policy["required"])
    self.assertEqual(policy["properties"]["require_human_labels"], {"const": True})
```

- [x] **Step 2: Write failing job contract tests**

```python
def test_factory_job_1_1_exposes_transaction_fields(self) -> None:
    schema = load_schema("factory_job.schema.json")
    self.assertEqual(schema["properties"]["schema_version"]["const"], "1.1.0")
    self.assertIn("PendingApproval", schema["properties"]["state"]["enum"])
    self.assertIn("Accepted", schema["properties"]["state"]["enum"])
    item = schema["$defs"]["jobItem"]
    self.assertIn("Attempting", item["properties"]["state"]["enum"])
    self.assertIn("Unknown", item["properties"]["state"]["enum"])
    self.assertIn("attempt_id", item["required"])
    self.assertFalse(schema["$defs"]["approvalRecord"]["additionalProperties"])
```

- [x] **Step 3: Run contract tests and verify RED**

Run:

```bash
python3 -m unittest tests.test_contracts tests.test_plan tests.test_ledger -v
```

Expected: failures identify schema version `1.0.0`, missing safety fields, missing transaction fields, and missing migration functions.

- [x] **Step 4: Define the migration module**

Create this public surface:

```python
import copy
from dataclasses import dataclass


@dataclass(frozen=True)
class MigrationResult:
    document: dict
    notes: tuple[str, ...]


def migrate_image_batch(document: object) -> MigrationResult:
    if not isinstance(document, dict):
        raise ValueError("image batch must be a JSON object")
    plan = copy.deepcopy(document)
    version = plan.get("schema_version")
    if version == "1.1.0":
        return MigrationResult(plan, ())
    if version != "1.0.0":
        raise ValueError(f"unsupported image batch schema_version {version!r}")
    plan["schema_version"] = "1.1.0"
    limits = plan.get("limits")
    if limits is None:
        limits = {"max_images": 20, "max_rounds": 3}
        plan["limits"] = limits
    if not isinstance(limits, dict):
        raise ValueError("image batch limits must be a JSON object")
    policy = plan.get("judge_policy")
    if policy is None:
        policy = {
            "min_dimension": 256,
            "reject_duplicates": True,
            "pass_threshold": 0.8,
        }
        plan["judge_policy"] = policy
    if not isinstance(policy, dict):
        raise ValueError("image batch judge_policy must be a JSON object")
    limits["require_approval_before_run"] = True
    policy["require_human_labels"] = True
    return MigrationResult(plan, ("migrated image batch 1.0.0 to 1.1.0",))


def migrate_factory_job(document: object) -> MigrationResult:
    if not isinstance(document, dict):
        raise ValueError("factory job must be a JSON object")
    job = copy.deepcopy(document)
    version = job.get("schema_version")
    if version == "1.1.0":
        return MigrationResult(job, ())
    if version != "1.0.0":
        raise ValueError(f"unsupported factory job schema_version {version!r}")
    job["schema_version"] = "1.1.0"
    if job.get("approval") is not None:
        raise ValueError("factory job 1.0.0 approval evidence cannot be migrated safely")
    if job.get("batch") is not None and not isinstance(job.get("batch"), dict):
        raise ValueError("factory job batch must be a JSON object or null")
    job["approval"] = {"current": None, "history": []}
    job["evaluation"] = None
    job["optimization"] = None
    items = job.get("items", [])
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                item.setdefault("attempt_id", None)
                item.setdefault("attempt_started_at", None)
    return MigrationResult(job, ("migrated factory job 1.0.0 to 1.1.0",))
```

Migration rules:

- Deep-copy input before mutation.
- Return an unchanged copy and empty notes for 1.1.0.
- For plan 1.0.0, set version 1.1.0, force `require_approval_before_run` and `require_human_labels` to `true`, and emit one migration note.
- For job 1.0.0, set version 1.1.0; convert `approval: null` to `{"current": null, "history": []}`; add `evaluation: null` and `optimization: null`; add nullable attempt fields to every item; preserve observed item outcomes and history.
- Reject missing, non-string, or unsupported versions with `ValueError`.
- Never mutate the caller-owned dictionary.

- [x] **Step 5: Update both schemas**

Use only keywords supported by `scripts/schema_lite.py`. Add closed definitions for `batchRecord`, `approvalRecord`, `approvalLedger`, `evaluationRecord`, `optimizationRecord`, and the expanded `jobItem`. Use a 64-character lowercase hexadecimal pattern for hashes and `date-time` for timestamps.

Add `job_already_running` and `recovery_required` to the closed job error-category enum.

- [x] **Step 6: Integrate migration at both schema entry points**

Call `migrate_image_batch` before plan schema validation. Call
`migrate_factory_job` before ledger schema validation. New plans and jobs are
written as 1.1.0; 1.0.0 inputs are upgraded in memory and are persisted as 1.1.0
only by the next authorized mutation. This keeps Task 1 independently green
after the schema version change.

```python
plan_migration = contract_migrations.migrate_image_batch(document)
schema_errors = schema_lite.validate(plan_migration.document, PLAN_SCHEMA)

job_migration = contract_migrations.migrate_factory_job(json.loads(raw))
payload = _assert_well_formed(job_migration.document)
```

- [x] **Step 7: Implement migrations and make focused tests green**

Run:

```bash
python3 -m unittest tests.test_contract_migrations tests.test_contracts tests.test_plan tests.test_ledger -v
```

Expected: migrated documents validate as 1.1.0; original dictionaries remain byte-equivalent when serialized canonically; no historical approval is invented.

- [x] **Step 8: Run the full regression suite**

```bash
python3 -m unittest discover -s tests -v
```

Expected: all tests pass.

- [x] **Step 9: Commit the contract boundary**

```bash
git add schemas/image_batch.schema.json schemas/factory_job.schema.json scripts/contract_migrations.py scripts/plan_validator.py scripts/job_ledger.py tests/test_contract_migrations.py tests/test_contracts.py tests/test_plan.py tests/test_ledger.py
git commit -m "feat: define Image Factory transaction contracts"
```

### Task 2: Propagate human policy and bind a canonical plan hash

**Files:**
- Modify: `scripts/plan_validator.py:43-67,80-102,148-260`
- Modify: `scripts/image_factory_cli.py:105-169`
- Modify: `tests/test_plan.py:20-180`
- Modify: `tests/test_cli.py:128-161`

**Interfaces:**
- Consumes: the migrated 1.1.0 plan produced by Task 1
- Produces: `canonical_plan_sha256(result_fields: dict) -> str`
- Extends: `PlanResult.plan_sha256: str`
- Extends: `PlanResult.require_human_labels: bool`
- Extends: `PlanResult.migration_notes: tuple[str, ...]`
- Consumed later by: approval recording, run validation, evaluation, and status

- [x] **Step 1: Write failing plan-hash and policy tests**

```python
def test_human_label_policy_reaches_plan_result(self) -> None:
    result = validate_plan(valid_plan_1_1(), base_dir=self.base)
    self.assertTrue(result.require_human_labels)


def test_plan_hash_changes_when_reference_bytes_change(self) -> None:
    first = validate_plan(plan_with_reference(self.reference), base_dir=self.base)
    self.reference.write_bytes(second_png())
    second = validate_plan(plan_with_reference(self.reference), base_dir=self.base)
    self.assertNotEqual(first.plan_sha256, second.plan_sha256)


def test_semantically_identical_json_has_the_same_plan_hash(self) -> None:
    first = validate_plan(plan_a(), base_dir=self.base)
    second = validate_plan(same_plan_with_different_key_order(), base_dir=self.base)
    self.assertEqual(first.plan_sha256, second.plan_sha256)
```

Add the named test helpers next to the existing fixtures in `tests/test_plan.py`.
Each helper returns a complete schema-valid 1.1.0 dictionary;
`plan_with_reference` accepts a path and `second_png` returns distinct valid PNG
bytes.

- [x] **Step 2: Run focused tests and verify RED**

```bash
python3 -m unittest tests.test_plan tests.test_cli.ValidatePlanCommandTests tests.test_cli.QuoteCommandTests -v
```

Expected: `PlanResult` lacks the new fields and CLI output lacks the hash and human-label policy.

- [x] **Step 3: Implement semantic plan hashing**

```python
def canonical_plan_sha256(result_fields: dict) -> str:
    encoded = json.dumps(
        result_fields,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

Hash batch id, round, limits, judge policy, and each ordered item's id, prompt, reference hashes, and idempotency key. Do not hash JSON whitespace, local absolute reference paths, or migration-note prose.

- [x] **Step 4: Extend validation and read-only CLI output**

Read the migrated document already produced by Task 1. Add the three new frozen
fields to `PlanResult`. Expose `plan_sha256`, `require_human_labels`, and migration
notes from `validate-plan` and `quote` without writing a ledger.

- [x] **Step 5: Run focused and full tests**

```bash
python3 -m unittest tests.test_plan tests.test_cli.ValidatePlanCommandTests tests.test_cli.QuoteCommandTests -v
python3 -m unittest discover -s tests -v
```

Expected: all tests pass and existing reference-image argument/idempotency tests remain green.

- [x] **Step 6: Commit the plan identity**

```bash
git add scripts/plan_validator.py scripts/image_factory_cli.py tests/test_plan.py tests/test_cli.py
git commit -m "feat: bind Image Factory plans to verified hashes"
```

### Task 3: Extract atomic JSON writes and persist per-item receipts

**Files:**
- Create: `scripts/atomic_json.py`
- Create: `scripts/receipt_store.py`
- Create: `tests/test_atomic_json.py`
- Create: `tests/test_receipt_store.py`
- Modify: `scripts/job_ledger.py:186-219`
- Modify: `scripts/image_factory_cli.py:77-78,290-300,336-340`
- Modify: `tests/test_ledger.py:138-201`

**Interfaces:**
- Produces: `write_json_atomic(path: Path, payload: object) -> None`
- Produces: `receipt_directory(job_path: Path) -> Path`
- Produces: `write_receipt(job_path: Path, receipt: dict) -> Path`
- Produces: `load_verified_receipts(job_path: Path, destination_dir: Path) -> dict[str, dict]`
- Produces: `rebuild_manifest(job_path: Path, receipts: dict[str, dict]) -> Path`
- Consumed later by: run transaction, recovery, and evaluation

- [x] **Step 1: Write failing atomic-write tests**

```python
def test_failed_atomic_write_preserves_previous_document(self) -> None:
    self.target.write_text('{"revision":1}\\n', encoding="utf-8")
    with mock.patch("json.dump", side_effect=OSError("injected write failure")):
        with self.assertRaises(OSError):
            atomic_json.write_json_atomic(self.target, {"revision": 2})
    self.assertEqual(self.target.read_text(encoding="utf-8"), '{"revision":1}\\n')
    self.assertEqual(list(self.base.glob(".atomic-*.tmp")), [])
```

- [x] **Step 2: Write failing receipt-store tests**

```python
def test_manifest_is_rebuilt_from_verified_per_item_receipts(self) -> None:
    first = receipt_store.write_receipt(self.job, self.receipt("a" * 64))
    second = receipt_store.write_receipt(self.job, self.receipt("b" * 64))
    receipts = receipt_store.load_verified_receipts(self.job, self.destination)
    manifest = receipt_store.rebuild_manifest(self.job, receipts)
    self.assertEqual(len(json.loads(manifest.read_text(encoding="utf-8"))), 2)
    self.assertTrue(first.is_file())
    self.assertTrue(second.is_file())
```

Define `ReceiptStoreFixture.receipt(idempotency_key: str) -> dict` to create a
complete receipt pointing at a real PNG under the fixture destination. Also test
closed-schema validation, artifact hash verification, tamper refusal, and
duplicate idempotency-key refusal.

- [x] **Step 3: Run the new tests and verify RED**

```bash
python3 -m unittest tests.test_atomic_json tests.test_receipt_store -v
```

Expected: imports fail because the two modules do not exist.

- [x] **Step 4: Implement atomic JSON persistence**

`write_json_atomic` creates a same-directory temporary file, serializes with sorted keys and one trailing newline, flushes and fsyncs, calls `os.replace`, best-effort fsyncs the parent directory where supported, and removes the temporary file on every exception. Refactor `write_ledger` to validate and scrub before calling it.

- [x] **Step 5: Implement the receipt store**

```python
def receipt_directory(job_path: Path) -> Path:
    return Path(str(job_path) + ".receipts")


def receipt_path(job_path: Path, idempotency_key: str) -> Path:
    return receipt_directory(job_path) / f"{idempotency_key}.json"


def manifest_path(job_path: Path) -> Path:
    return Path(str(job_path) + ".receipts.json")
```

Validate each receipt against `schemas/artifact_receipt.schema.json`, recompute artifact hash, bytes, and dimensions through existing collector helpers, and index loaded receipts by idempotency key.

- [x] **Step 6: Replace direct receipt-manifest I/O**

Remove direct `Path.write_text` receipt-manifest writes and direct unverified loads from `image_factory_cli.py`. Evaluation reads only through `load_verified_receipts`.

- [x] **Step 7: Run focused and full tests**

```bash
python3 -m unittest tests.test_atomic_json tests.test_receipt_store tests.test_ledger tests.test_cli -v
python3 -m unittest discover -s tests -v
```

Expected: all tests pass.

- [x] **Step 8: Commit durable receipt storage**

```bash
git add scripts/atomic_json.py scripts/receipt_store.py scripts/job_ledger.py scripts/image_factory_cli.py tests/test_atomic_json.py tests/test_receipt_store.py tests/test_ledger.py
git commit -m "feat: persist image receipts atomically"
```

### Task 4: Serialize each job with a cross-platform process lock

**Files:**
- Create: `scripts/job_lock.py`
- Create: `tests/test_job_lock.py`
- Modify: `scripts/image_factory_cli.py:33-39,195-316,331-437`

**Interfaces:**
- Produces: `JobAlreadyRunningError`
- Produces: `JobLock(job_path: Path, timeout_seconds: float = 0.0)`
- Produces: `lock_path_for(job_path: Path) -> Path`
- Consumed later by: every mutating CLI command

- [x] **Step 1: Write the failing process-lock test**

Add `spawn_lock_holder(job_path: Path) -> multiprocessing.Process` to create a
`spawn`-context child that acquires the lock, signals `"locked"` through the
fixture queue, and waits on a release event. Use it rather than two lock objects
in one process:

```python
def test_second_process_cannot_acquire_the_same_job(self) -> None:
    process = self.spawn_lock_holder(self.job_path)
    self.assertEqual(self.ready.get(timeout=5), "locked")
    with self.assertRaises(job_lock.JobAlreadyRunningError):
        with job_lock.JobLock(self.job_path):
            self.fail("second process acquired active job")
    process.join(timeout=5)
    with job_lock.JobLock(self.job_path):
        pass
```

- [x] **Step 2: Run lock tests and verify RED**

```bash
python3 -m unittest tests.test_job_lock -v
```

Expected: import failure because `job_lock` does not exist.

- [x] **Step 3: Implement the standard-library lock adapters**

The context manager owns one open `a+b` handle until exit. Ensure the file has at least one byte before Windows locking. Use `fcntl.flock(handle, LOCK_EX | LOCK_NB)` on Unix and `msvcrt.locking(handle.fileno(), LK_NBLCK, 1)` on Windows. Translate only contention errors to `JobAlreadyRunningError`; propagate unrelated I/O errors. Unlock in `__exit__` and always close the handle.

- [x] **Step 4: Add stable CLI contention behavior**

```python
EXIT_JOB_LOCKED = 5
EXIT_RECOVERY_REQUIRED = 6
```

Wrap `run`, `evaluate`, `optimize`, and the later `recover` command in `JobLock`. Return `error_category: job_already_running` and spend zero calls on contention. Leave `status` lock-free because it does not mutate and ledger replacement is atomic.

- [x] **Step 5: Run lock, CLI, and full tests**

```bash
python3 -m unittest tests.test_job_lock tests.test_cli -v
python3 -m unittest discover -s tests -v
```

Expected: all tests pass on the current host.

- [x] **Step 6: Commit job serialization**

```bash
git add scripts/job_lock.py scripts/image_factory_cli.py tests/test_job_lock.py tests/test_cli.py
git commit -m "feat: serialize Image Factory jobs"
```

### Task 5: Add approval history and an explicit attempt lifecycle

**Files:**
- Modify: `scripts/job_ledger.py:52-114,129-147,227-325`
- Modify: `tests/test_ledger.py:51-284`
- Modify: `schemas/factory_job.schema.json`

**Interfaces:**
- Produces: `bind_plan(plan_sha256: str, round_number: int, image_count: int) -> dict`
- Produces: `record_approval(plan_sha256: str, round_number: int, image_count: int, source: str) -> dict`
- Produces: `approval_matches(plan_sha256: str, round_number: int, image_count: int) -> bool`
- Produces: `start_attempt(item: PlanItem, attempt_id: str) -> dict`
- Produces: `complete_attempt(item: PlanItem, attempt_id: str, receipt_id: str) -> dict`
- Produces: `fail_attempt(item: PlanItem, attempt_id: str, error_category: str) -> dict`
- Produces: `mark_attempt_unknown(item_id: str, attempt_id: str) -> dict`
- Preserves: `pending_items(items: object) -> list`, narrowed to never-recorded keys

- [ ] **Step 1: Write failing approval and attempt tests**

```python
def test_attempt_is_counted_once_when_it_starts(self) -> None:
    started = self.ledger.start_attempt(self.item, "attempt-1")
    completed = self.ledger.complete_attempt(self.item, "attempt-1", "receipt-1")
    self.assertEqual(started["items"][0]["attempts"], 1)
    self.assertEqual(completed["items"][0]["attempts"], 1)


def test_unknown_attempt_is_never_pending(self) -> None:
    self.ledger.start_attempt(self.item, "attempt-1")
    self.ledger.mark_attempt_unknown(self.item.id, "attempt-1")
    self.assertEqual(self.ledger.pending_items((self.item,)), [])


def test_approval_is_bound_to_exact_plan_and_count(self) -> None:
    self.ledger.record_approval("a" * 64, 1, 2, "run_approve_flag")
    self.assertTrue(self.ledger.approval_matches("a" * 64, 1, 2))
    self.assertFalse(self.ledger.approval_matches("b" * 64, 1, 2))
    self.assertFalse(self.ledger.approval_matches("a" * 64, 1, 1))
```

- [ ] **Step 2: Write failing state-machine tests**

Assert `PlanValidated -> Running`, `Unknown -> Running`, and `Completed -> Running` are illegal. Assert `Evaluated -> PendingApproval`, `Evaluated -> Accepted`, and `Evaluated -> Optimized` are legal. Assert `Accepted` and `Failed` are terminal.

- [ ] **Step 3: Run ledger tests and verify RED**

```bash
python3 -m unittest tests.test_ledger -v
```

Expected: new methods and states are absent and current unsafe transitions are accepted.

- [ ] **Step 4: Implement plan binding and approval history**

`bind_plan` stores only `batch_id`, round, plan hash, and image count; it stores
no prompts or local paths. `record_approval` appends the specification's record
and sets `approval.current`. It accepts only `run_approve_flag` as source, which
records the fact the CLI can prove. Binding a different plan clears only current
approval and preserves history.

- [ ] **Step 5: Implement attempt lifecycle methods**

`start_attempt` creates or updates one item by idempotency key, increments attempts exactly once, records an RFC 3339 start time, and refuses a key already in `Attempting`, `Generated`, `Failed`, `Skipped`, or `Unknown`. Completion and failure require the same active attempt id and never increment attempts.

- [ ] **Step 6: Replace the state transition table**

Encode the specification's state diagram. Keep partial-job conditions in CLI orchestration, while the base table rejects every direct transition that can turn `Unknown`, `Completed`, or `Evaluated` into `Running`.

- [ ] **Step 7: Run focused and full tests**

```bash
python3 -m unittest tests.test_ledger tests.test_contracts -v
python3 -m unittest discover -s tests -v
```

Expected: every persisted ledger validates as 1.1.0 and all tests pass.

- [ ] **Step 8: Commit the ledger transaction model**

```bash
git add scripts/job_ledger.py schemas/factory_job.schema.json tests/test_ledger.py tests/test_contracts.py
git commit -m "feat: record approvals and generation attempts"
```

### Task 6: Make `run` a crash-safe allowance transaction

**Files:**
- Modify: `scripts/image_factory_cli.py:172-316,447-504`
- Modify: `tests/fakes/fake_codex.py:1-161`
- Modify: `tests/test_cli.py:163-267`
- Create: `tests/test_run_crash_recovery.py`
- Create: `tests/test_run_concurrency.py`

**Interfaces:**
- Consumes: plan hash, `JobLock`, approval history, attempt lifecycle, and receipt store
- Produces: `ApprovalRequiredError`, `RunStateError`, `prepare_run(...)`, and `require_runnable_state(...)`
- Produces: one external invocation per newly approved pending idempotency key
- Produces: `job_already_running` and `recovery_required` refusal payloads
- Preserves: `generation_runner.run_item(...) -> GenerationOutcome`

- [ ] **Step 1: Write failing approval-binding CLI tests**

Test that `run --approve` records the exact plan hash, round, and remaining count before the first fake invocation; changing the plan requires a new approval; and running without approval produces no invocation evidence. Assert the ledger stores neither prompt text nor reference paths.

- [ ] **Step 2: Write one failing crash test per durability boundary**

Use `unittest.mock.patch` to raise `KeyboardInterrupt`:

1. Before `start_attempt`.
2. From `generation_runner.run_item` after fake invocation evidence exists.
3. From `receipt_store.write_receipt` after artifact publication.
4. From `JobLedger.complete_attempt` after receipt persistence.
5. From `receipt_store.rebuild_manifest` after ledger completion.

Reopen the job after every interruption and assert the specification's crash-matrix result. No ambiguous idempotency key may become pending.

- [ ] **Step 3: Extend the fake generator with invocation evidence**

Accept these optional control fields:

```json
{
  "invocation_dir": "path supplied by the test",
  "delay_before_result_seconds": 0.5
}
```

At process start, atomically create one uniquely named JSON file in `invocation_dir` containing process id and argv. Delay only after writing that evidence. Preserve all existing modes.

- [ ] **Step 4: Write the failing two-process test**

Launch two real `bin/image-factory run` processes against the same two-item plan and delayed fake generator:

```python
self.assertEqual(
    sorted(result.returncode for result in results),
    [0, cli.EXIT_JOB_LOCKED],
)
self.assertEqual(len(list(self.invocation_dir.glob("*.json"))), 2)
self.assertEqual(len(receipts_for_unique_idempotency_keys()), 2)
```

The winning process legitimately invokes two planned items; the losing process invokes none.
Define `receipts_for_unique_idempotency_keys() -> set[str]` in the test to load
the per-item receipt files and return their `idempotency_key` values.

- [ ] **Step 5: Run crash and concurrency tests and verify RED**

```bash
python3 -m unittest tests.test_run_crash_recovery tests.test_run_concurrency -v
```

Expected: current CLI loses receipt continuity, exposes ambiguous work incorrectly, or allows both processes to proceed.

- [ ] **Step 6: Replace `_drive_to_running` with guarded preparation**

```python
def prepare_run(
    ledger: JobLedger,
    plan: PlanResult,
    approved: bool,
) -> list[PlanItem]:
    pending = ledger.pending_items(plan.items)
    require_runnable_state(ledger.read(), pending)
    ledger.bind_plan(plan.plan_sha256, plan.round, len(pending))
    if pending and not approved:
        raise ApprovalRequiredError(len(pending))
    if pending:
        ledger.record_approval(
            plan.plan_sha256,
            plan.round,
            len(pending),
            "run_approve_flag",
        )
        state = JobState(ledger.read()["state"])
        if state in (JobState.DRAFT, JobState.OPTIMIZED, JobState.PARTIAL):
            ledger.transition(JobState.PLAN_VALIDATED)
        ledger.transition(JobState.APPROVED)
        ledger.transition(JobState.RUNNING)
    return pending
```

Refuse `Running`, `Completed`, `Evaluated`, `PendingApproval`, `Unknown`, `Accepted`, and `Failed`. Permit `Partial` only when it has unattempted items, no unknown item, no active limit, and a fresh approval for the remaining count.

- [ ] **Step 7: Implement the exact transaction order**

```python
attempt_id = uuid.uuid4().hex
ledger.start_attempt(item, attempt_id)
outcome = generation_runner.run_item(...)
if not outcome.ok:
    if outcome.failure.code in ("timeout", "artifact_missing"):
        ledger.mark_attempt_unknown(item.id, attempt_id)
    else:
        ledger.fail_attempt(item, attempt_id, _error_category(outcome.failure.code))
else:
    collected = artifact_collector.collect_artifact(...)
    if not collected.ok:
        ledger.fail_attempt(item, attempt_id, classified_error)
    else:
        receipt_store.write_receipt(job_path, collected.receipt)
        ledger.complete_attempt(
            item,
            attempt_id,
            collected.receipt["artifact_id"],
        )
```

After the loop, load verified per-item receipts, rebuild the manifest atomically, and transition to `Completed` or `Partial`. Do not catch `KeyboardInterrupt`; the durable attempt state is the evidence recovery needs.

If any item becomes `Unknown`, stop the loop and transition the batch to
`Unknown`. Do not attempt later items because the current transaction has an
unresolved external outcome.

- [ ] **Step 8: Run focused and full tests**

```bash
python3 -m unittest tests.test_cli tests.test_run_crash_recovery tests.test_run_concurrency -v
python3 -m unittest discover -s tests -v
```

Expected: every crash case matches the matrix and two processes produce one winning batch.

- [ ] **Step 9: Commit crash-safe generation**

```bash
git add scripts/image_factory_cli.py tests/fakes/fake_codex.py tests/test_cli.py tests/test_run_crash_recovery.py tests/test_run_concurrency.py
git commit -m "feat: make generation calls crash safe"
```

### Task 7: Persist evaluation, human decisions, optimization, and status

**Files:**
- Modify: `scripts/image_factory_cli.py:319-437,475-504`
- Modify: `scripts/evaluator.py:90-183`
- Modify: `scripts/optimizer.py:1-260`
- Modify: `tests/test_cli.py:269-470`
- Modify: `tests/test_evaluator.py:180-270`
- Modify: `tests/test_optimizer.py:1-330`
- Modify: `tests/test_ledger.py`

**Interfaces:**
- Consumes: `PlanResult.require_human_labels`, verified receipts, and locked ledger
- Produces: `record_evaluation(scores_sha256: str, decision: str) -> dict`
- Produces: `record_optimization(plan_sha256: str, round_number: int) -> dict`
- Extends: `optimize --job JOB`
- Extends: `status` with plan, approval, counts, evaluation, and optimization

- [ ] **Step 1: Write the failing human-label propagation test**

Extend `CliFixture` with `run_approved_batch`, `evaluate_without_labels`, and
`read_job` helpers. They must call the real CLI handler, parse JSON output, and
read the temporary ledger rather than fabricating state. Then add:

```python
def test_required_human_labels_cannot_pass_unlabeled(self) -> None:
    self.fixture.write_plan(plan_requiring_human_labels())
    self.fixture.run_approved_batch()
    code, payload = self.fixture.evaluate_without_labels()
    self.assertEqual(code, 0)
    self.assertEqual(payload["decision"], "pending_approval")
    self.assertEqual(self.fixture.read_job()["state"], "PendingApproval")
```

Also test whole-batch approval, partial labels remaining pending, and one rejection causing `fail` regardless of advisory score.

- [ ] **Step 2: Write failing evaluate/optimize state tests**

Assert that evaluation writes scores atomically and stores their hash; deterministic failure leaves `Evaluated`; fully approved passing work becomes `Accepted`; optimize requires `--job`; mismatched batch/round/plan is refused; successful optimization stores the next-plan hash and enters `Optimized`.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
python3 -m unittest tests.test_cli.EvaluateAndOptimizeCommandTests tests.test_evaluator tests.test_optimizer -v
```

Expected: evaluation hardcodes human labels off, no ledger state changes, and optimize has no job argument.

- [ ] **Step 4: Propagate human policy and persist scores atomically**

Pass `result.require_human_labels` to `evaluate_batch`. Write scores through `atomic_json.write_json_atomic`, hash the persisted bytes, and record evaluation under the job lock. Map `pass` to `Accepted`, `pending_approval` to `PendingApproval`, and `fail` to `Evaluated`.

- [ ] **Step 5: Bind optimization to job evidence**

Add:

```python
optimize.add_argument("--job", required=True)
```

Require `Evaluated`, verify batch id and round, write and validate the next plan atomically, hash it through `plan_validator`, record optimization, clear current approval, and transition to `Optimized`.

Verify that the supplied scores file hash equals `evaluation.scores_sha256`.
Build the next plan from the migrated 1.1.0 current plan so every optimizer output
also declares schema version 1.1.0.

- [ ] **Step 6: Expand status without leaking content**

Return batch hash and round, current approval summary and history count, generated/failed/pending/unknown counts, evaluation, optimization, limit, and error category. Do not return raw prompts, reference paths, environment paths, or full approval history by default.

- [ ] **Step 7: Run focused and full tests**

```bash
python3 -m unittest tests.test_cli tests.test_evaluator tests.test_optimizer tests.test_ledger -v
python3 -m unittest discover -s tests -v
```

Expected: all tests pass and required-human-label work cannot pass unlabeled.

- [ ] **Step 8: Commit the state loop**

```bash
git add scripts/image_factory_cli.py scripts/evaluator.py scripts/optimizer.py tests/test_cli.py tests/test_evaluator.py tests/test_optimizer.py tests/test_ledger.py
git commit -m "feat: persist evaluation and human decisions"
```

### Task 8: Add non-spending reconciliation and safe recovery

**Files:**
- Modify: `scripts/image_factory_cli.py:420-504`
- Create: `tests/test_recovery.py`
- Modify: `skills/codex-image-factory-recover/SKILL.md:16-105`
- Modify: `skills/codex-image-factory-run/SKILL.md`
- Modify: `tests/test_skills.py:160-220`

**Interfaces:**
- Produces: `recover --plan PLAN --job JOB --destination DIR`
- Produces: `RecoveryReport(state: str, reconciled: tuple[str, ...], unknown: tuple[str, ...], pending_count: int, remaining_generation_calls: int)`
- Consumes: job lock, plan hash, receipt verification, and ledger attempt records
- Makes: zero Codex calls

- [ ] **Step 1: Write failing recovery tests**

Cover `Attempting` plus valid receipt becoming `Generated`; `Attempting` without receipt becoming `Unknown`; `Unknown` plus valid receipt becoming `Generated`; manifest rebuild; tampered receipt refusal; unresolved unknown blocking run; and zero fake invocation evidence.

- [ ] **Step 2: Run recovery tests and verify RED**

```bash
python3 -m unittest tests.test_recovery -v
```

Expected: `recover` and `RecoveryReport` do not exist.

- [ ] **Step 3: Implement `recover`**

Under the job lock, validate the plan, load verified receipts, reconcile item records, rebuild the manifest, and derive `Completed`, `Partial`, or `Unknown`. If any item remains unknown, return `EXIT_RECOVERY_REQUIRED`. Never call `generation_runner`.

- [ ] **Step 4: Update recovery and run Skills**

The recovery Skill calls `status`, `validate-plan`, then `recover`. It reports completed, failed, pending, and unknown counts plus one legal next action. Remove the direct-resume instruction for stale `Running`. The run Skill quotes remaining calls and obtains fresh approval before a safe partial resume.

- [ ] **Step 5: Run focused and full tests**

```bash
python3 -m unittest tests.test_recovery tests.test_skills tests.test_cli -v
python3 -m unittest discover -s tests -v
```

Expected: all tests pass and recovery creates no invocation evidence.

- [ ] **Step 6: Commit non-spending recovery**

```bash
git add scripts/image_factory_cli.py tests/test_recovery.py skills/codex-image-factory-recover/SKILL.md skills/codex-image-factory-run/SKILL.md tests/test_skills.py
git commit -m "feat: reconcile interrupted image jobs safely"
```

### Task 9: Align the shared conversation contract

**Files:**
- Modify: `skills/codex-image-factory-use/SKILL.md`
- Modify: `skills/codex-image-factory-run/SKILL.md`
- Modify: `skills/codex-image-factory-judge/SKILL.md`
- Modify: `skills/codex-image-factory-recover/SKILL.md`
- Modify: `skills/codex-image-factory-use/references/conversation-workflow.md`
- Modify: `skills/codex-image-factory-use/references/conversation-examples.md`
- Modify: `skills/codex-image-factory-use/references/conversation-anti-patterns.md`
- Modify: `skills/codex-image-factory-use/references/conversation-faq.md`
- Modify: `tests/test_conversation_workflow.py`
- Modify: `tests/test_skills.py`

**Interfaces:**
- Consumes: quote, plan hash, approval record, result numbers, status counts, and recovery report
- Produces: natural-language approval mapped only to the displayed plan and round
- Preserves: recommendation-first and at-most-three-directions behavior

- [ ] **Step 1: Write failing conversation assertions**

Require the shared contract to name plan-bound approval, remaining generation calls, approval invalidation after plan changes, `PendingApproval`, `Accepted`, `Unknown`, and non-spending recovery. Require all four Skills to route to the shared contract.

- [ ] **Step 2: Run conversation tests and verify RED**

```bash
python3 -m unittest tests.test_conversation_workflow tests.test_skills -v
```

Expected: existing dialogue documents lack the new transaction and recovery terms.

- [ ] **Step 3: Update the shared conversation workflow**

Specify this user-visible sequence:

1. Recommend a direction.
2. Present one compact confirmation card with round and call count.
3. Accept approval only for that card.
4. Generate and present numbered results.
5. Map group, partial, and per-image decisions to human labels.
6. Require a new card and approval for every rewritten round.
7. Report ambiguous recovery without suggesting a diagnostic rerun.

Keep file-lock, schema-version, hash, and receipt-directory details out of normal user copy.

- [ ] **Step 4: Update examples, anti-patterns, FAQ, and four Skills**

Include a first round, a partial approval, a changed plan that invalidates approval, and an interrupted job with an unresolved item. Preserve exact natural-language forms such as `整组批准` and `第 3 张改成更温暖`.

- [ ] **Step 5: Run focused, distribution, and full tests**

```bash
python3 -m unittest tests.test_conversation_workflow tests.test_skills tests.test_distribution_extended tests.test_ownership_boundary -v
python3 -m unittest discover -s tests -v
```

Expected: all tests pass; documentation retains the image-only ownership boundary.

- [ ] **Step 6: Commit the transactional conversation**

```bash
git add skills/codex-image-factory-use skills/codex-image-factory-run/SKILL.md skills/codex-image-factory-judge/SKILL.md skills/codex-image-factory-recover/SKILL.md tests/test_conversation_workflow.py tests/test_skills.py
git commit -m "docs: bind image conversations to approved rounds"
```

### Task 10: Add cross-platform CI and release evidence gates

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `tests/test_cli.py:20-34`
- Modify: `tests/test_distribution.py`
- Modify: `tests/test_distribution_extended.py:30-43,94-143`
- Modify: `scripts/validate_distribution.py`
- Modify: `docs/verification/offline.md`
- Modify: `docs/verification/runtime.md`
- Modify: `docs/Codex-Image-Factory-Plugin-Architecture.md`
- Modify: `docs/Codex-Image-Factory-Plugin-Architecture.zh_CN.md`
- Modify: `docs/Codex-Image-Factory-Plugin-Technical-Solution.md`
- Modify: `docs/Codex-Image-Factory-Plugin-Technical-Solution.zh_CN.md`

**Interfaces:**
- Produces: one CI workflow running tests and distribution checks on supported hosts
- Produces: version-specific runtime evidence with no stale SHA or release number
- Preserves: standard-library-only runtime and pinned upstream snapshot checks

- [ ] **Step 1: Make the fake Codex launcher portable**

Update `build_shim` to create a shell launcher on Unix and a `.cmd` launcher on Windows. Add a test asserting the selected launcher suffix and executable invocation for the active platform.

- [ ] **Step 2: Add the CI workflow**

Use this matrix:

```yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    python-version: ["3.11", "3.13"]
```

Each job checks out the repository, configures Python, runs `python -m compileall -q scripts tests`, runs `python -m unittest discover -s tests -v`, runs `python scripts/validate_distribution.py .`, and runs `git diff --check`. No job installs runtime dependencies.

- [ ] **Step 3: Add CI/distribution contract tests**

Assert the workflow contains all three operating systems, both Python versions, the full suite, distribution validation, and compile check. Assert runtime evidence names version 0.1.2 and has explicit `PASS`, `FAIL`, or `NOT_RUN` for each external gate.

- [ ] **Step 4: Refresh architecture and verification documents**

Document the lock, attempt states, per-item receipt source of truth, approval hash, recovery refusal, schema migration, human label enforcement, and CI matrix. Replace old remote SHA/version evidence only with freshly observed results; otherwise mark the gate `NOT_RUN`.

- [ ] **Step 5: Run all offline gates**

```bash
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -v
python3 scripts/validate_distribution.py .
git diff --check
```

Expected: all commands exit zero.

- [ ] **Step 6: Commit CI and evidence structure**

```bash
git add .github/workflows/ci.yml tests/test_cli.py tests/test_distribution.py tests/test_distribution_extended.py scripts/validate_distribution.py docs/verification docs/Codex-Image-Factory-Plugin-Architecture.md docs/Codex-Image-Factory-Plugin-Architecture.zh_CN.md docs/Codex-Image-Factory-Plugin-Technical-Solution.md docs/Codex-Image-Factory-Plugin-Technical-Solution.zh_CN.md
git commit -m "ci: gate Image Factory production evidence"
```

### Task 11: Version, publish, reinstall, and perform final acceptance

**Files:**
- Modify: `.codex-plugin/plugin.json:2-4`
- Modify: `CHANGELOG.md:3-17`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `docs/verification/runtime.md`
- Modify: `tests/test_distribution.py`
- Modify: `tests/test_distribution_extended.py`

**Interfaces:**
- Produces: clean, tagged `v0.1.2` source and matching remote branch
- Produces: freshly installed `codex-image-factory@partme-ai-image-factory` 0.1.2
- Requires separate authorization before uninstall/reinstall, push/tag, or paid canary

- [ ] **Step 1: Add failing version-alignment tests**

Assert plugin manifest, changelog, architecture documents, runtime evidence, and distribution output agree on 0.1.2. Assert runtime evidence cannot retain the prior remote SHA as the current release SHA.

- [ ] **Step 2: Bump release metadata and changelog**

Set manifest version to `0.1.2`. Add a changelog entry covering plan-bound approval, process locking, attempt lifecycle, per-item receipts, reconciliation, human-label enforcement, state transitions, schema migration, and CI.

- [ ] **Step 3: Run the complete local release gate**

```bash
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -v
python3 scripts/validate_distribution.py .
bin/image-factory probe --json
git diff --check
git status --short
```

Expected: compile, tests, validation, probe, and diff check pass. Status lists only intended release changes. The current Codex CLI does not expose `plugin validate`, so do not report that nonexistent command as passed.

- [ ] **Step 4: Review the complete change before publication**

Use `superpowers:requesting-code-review`. Resolve every correctness, compatibility, security, concurrency, and recovery finding, then rerun Step 3. Confirm no user-owned dirty file was lost or silently folded into an unrelated commit.

- [ ] **Step 5: Commit the release candidate**

```bash
git add .codex-plugin/plugin.json CHANGELOG.md README.md README.zh-CN.md docs/verification/runtime.md tests/test_distribution.py tests/test_distribution_extended.py
git commit -m "release: prepare Codex Image Factory 0.1.2"
```

- [ ] **Step 6: Obtain authorization and publish the release candidate**

Show the commit list, local HEAD, upstream branch, and planned validation actions.
After explicit push authorization, publish `main` without creating the final tag:

```bash
git push origin main
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main
git ls-remote origin refs/heads/main
```

Expected: local HEAD, `origin/main`, and remote main are identical. The commit is
still a release candidate until the remaining gates pass.

- [ ] **Step 7: Verify remote CI**

Wait for the GitHub Actions workflow associated with the published commit. Record job URLs or run identifiers and per-platform conclusions in `docs/verification/runtime.md`. Do not label a queued or partially completed matrix as passed.

- [ ] **Step 8: Obtain authorization and perform a clean reinstall**

Removing the installed plugin deletes its cache, so ask explicitly before this step. After authorization:

```bash
codex plugin marketplace upgrade partme-ai-image-factory
codex plugin remove codex-image-factory@partme-ai-image-factory --json
codex plugin add codex-image-factory@partme-ai-image-factory --json
codex plugin list
```

Expected: version 0.1.2 is installed and enabled; the cache is clean and resolves
to the release-candidate commit without manual edits.

- [ ] **Step 9: Run a fresh no-spend conversational smoke**

Start a new Codex session that explicitly reads `codex-image-factory-use`. Ask for a small image series and verify that the response recommends a direction, displays round and call count, and waits for explicit approval. Verify `probe`, `validate-plan`, `quote`, `status`, and `recover` are reachable without making an image call.

- [ ] **Step 10: Gate the paid canary separately**

Show the exact plan, image count, and maximum generation-call count. Only after a
new explicit authorization, run the smallest useful canary, verify per-item
receipts and ledger transitions, collect human labels, and confirm the final state
is `Accepted`. If authorization is not given, record `paid_canary = NOT_RUN`,
retain release-candidate status, and stop before the production-ready tag.

- [ ] **Step 11: Record candidate evidence, commit it, and rerun remote CI**

Update runtime evidence with the candidate implementation SHA, remote CI run,
installed candidate version and cache commit, fresh-session smoke, and paid-canary
result. Then:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_distribution.py .
git diff --check
git add docs/verification/runtime.md
git commit -m "test: record Image Factory 0.1.2 acceptance"
git push origin main
```

Wait for the evidence commit's CI matrix and require every job to pass. Do not
write that commit's own SHA into a file inside the same commit; final SHA parity is
verified by commands in the next step.

- [ ] **Step 12: Tag the final verified commit**

Show the final HEAD and successful CI run. After explicit tag authorization:

```bash
git fetch origin main --tags
git rev-parse HEAD
git rev-parse origin/main
git tag -a v0.1.2 -m "Codex Image Factory 0.1.2"
git push origin v0.1.2
git rev-list -n 1 v0.1.2
git ls-remote origin refs/heads/main refs/tags/v0.1.2 "refs/tags/v0.1.2^{}"
```

Expected: local HEAD, `origin/main`, remote main, and dereferenced `v0.1.2`
commit are identical.

- [ ] **Step 13: Reinstall the final commit and prove parity**

The evidence commit changes the marketplace revision, so ask again before
deleting the candidate cache. After authorization:

```bash
codex plugin marketplace upgrade partme-ai-image-factory
codex plugin remove codex-image-factory@partme-ai-image-factory --json
codex plugin add codex-image-factory@partme-ai-image-factory --json
codex plugin list
git rev-parse HEAD
git rev-parse origin/main
git rev-list -n 1 v0.1.2
```

Expected: installed version is 0.1.2; its cache commit, local HEAD, upstream main,
remote main, and tag commit match. Report the final read-only parity evidence in
the completion response.

## Completion Gate

```text
plan_schema_1_1 = PASS
job_schema_1_1 = PASS
schema_migration = PASS
plan_hash_binding = PASS
human_label_propagation = PASS
approval_audit_history = PASS
job_process_lock = PASS on Linux/macOS/Windows
attempt_lifecycle = PASS
per_item_receipt_atomicity = PASS
crash_matrix = PASS
concurrent_double_spend_guard = PASS
unknown_retry_refusal = PASS
evaluation_state = PASS
optimization_state = PASS
conversation_contract = PASS
full_source_tests = PASS
distribution_validation = PASS
remote_ci_matrix = PASS
remote_sha_parity = PASS
fresh_marketplace_install = PASS
fresh_session_no_spend_smoke = PASS
paid_canary = PASS
```

## Stop Conditions

- Stop before generation if approval does not match the exact current plan hash, round, and remaining count.
- Stop recovery with `Unknown` if receipt evidence cannot prove whether a call completed.
- Stop a second writer with `job_already_running`.
- Stop the production-ready tag if any test, platform, schema, source/tag/remote
  parity, clean-install, or paid-canary gate fails.
- Stop before uninstall/reinstall, push/tag, or paid canary until the user explicitly authorizes that operation.
