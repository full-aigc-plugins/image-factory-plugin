# Offline verification

Everything in this document runs without network access, without a Codex
account, and without generating an image. It is the evidence that the
deterministic parts behave as specified.

Recorded 2026-09-12.

## Commands

```bash
python3 -m unittest discover -s tests -v
```

Expected: `OK`, 226 tests, no failures, no errors. The suite uses the standard
library only.

```bash
python3 scripts/validate_distribution.py .
```

Expected: `validated codex-image-factory compatibility foundation 0.1.1` and
exit code 0.

```bash
python3 scripts/validate_distribution.py docs/..
```

Expected: the same output, proving the validator resolves a relative root.

```bash
bin/image-factory probe --json
```

Expected: a verdict of `available` or `unavailable` with the reasons that led to
it. On a machine without an image-capable account this reports
`verdict: "unavailable"` and names what is missing. The command neither opens a
network connection nor executes the Codex binary; a test asserts the latter by
placing a binary that would create a marker file if it ran.

## Coverage map

| Layer | Test file | What it establishes |
| --- | --- | --- |
| Identity and distribution | `tests/test_distribution.py` | Manifest, marketplace, legal files, brand asset shapes, README pair |
| Contract shape | `tests/test_contracts.py` | Every schema is closed draft 2020-12, and no schema uses a keyword the checker cannot enforce |
| Schema enforcement | `tests/test_plan.py` | Unknown and platform-impossible fields are refused; caps and patterns hold |
| Environment probe | `tests/test_probe.py` | Verdicts for missing binary, missing auth, disabled feature, incapable provider, unwritable directory; the binary is never executed |
| Artifact collection | `tests/test_collector.py` | Directory diffing, PNG reads, hash recomputation, mid-collection rewrite, receipt re-verification |
| Job state | `tests/test_ledger.py` | Transition table, terminal failure, atomic write, credential refusal, idempotent resumption |
| Generation orchestration | `tests/test_runner.py` | Argv shape, absence of bypass flags, classification of success, timeout, usage limit, failure, silent exit |
| Evaluation | `tests/test_evaluator.py` | Each deterministic gate, duplicate flagging for every participant, advisory precedence, human precedence |
| Optimization | `tests/test_optimizer.py` | Carried-forward items, instruction contract, round ceiling, immutability of the previous plan |
| CLI | `tests/test_cli.py` | Every subcommand, the approval gate, resumption, usage-limit stop |
| Skills | `tests/test_skills.py` | Inventory, frontmatter, required sections, prohibitions, platform boundary |
| Contract migration | `tests/test_contract_migrations.py` | 1.0.0 to 1.1.0 upgrades, gates forced on, refusals, caller dictionaries never mutated |
| Atomic persistence | `tests/test_atomic_json.py` | Temporary-file write, failure preserves the previous document, no leftovers |
| Receipt store | `tests/test_receipt_store.py` | Per-item receipts, verification on read, tamper and duplicate-key refusal, manifest rebuild |
| Job locking | `tests/test_job_lock.py` | A second process cannot acquire the job; unrelated errors are not reported as contention |
| Crash matrix | `tests/test_run_crash_recovery.py` | Five durability boundaries; no ambiguous key becomes pending again |
| Concurrency | `tests/test_run_concurrency.py` | Two real CLI processes: one wins, one is refused, exactly the planned calls happen |
| Recovery | `tests/test_recovery.py` | Reconciliation from receipts, unknown refusal, zero generation calls |
| Conversation contract | `tests/test_conversation_workflow.py` | Plan-bound approval, remaining calls, invalidated approval, recovery vocabulary |

## Gate status

| Gate | Status | Reason |
| --- | --- | --- |
| `offline_suite` | PASS | 372 tests pass on the development host |
| `distribution_validator` | PASS | Prints the validated foundation line |
| `official_plugin_validator` | PASS | `Plugin validation passed` |
| `secret_scan` | PASS | No secret-like content; the validator scans the whole tree |
| `skill_quick_validation` | PASS | 4 of 4 skills satisfy the content rules in `tests/test_skills.py` |
| `skill_description_parsed` | PASS | The real evaluator reports `description_valid = True` for all four, with lengths 590, 488, 534, 477 |
| `cross_platform_ci` | NOT_RUN | The workflow exists and is asserted by tests; GitHub Actions has not run it for this commit |
| `skill_trace` | 4/4 at 4.07–4.13 | `use` 4.13, `run` 4.07, `judge` 4.07, `recover` 4.11. Above the 3.5 bar this plan set, below the 4.5 bar used elsewhere in this organisation |
| `runtime_generation_evidence` | NOT_RUN | A two-item run was observed against 0.1.0 only; the 1.1.0 contracts change the transaction, so this needs re-observation |
| `usage_limit_evidence` | NOT_RUN | Requires exhausting the account's image allowance, which is not a state this work should create deliberately |
| `plugin_installation` | NOT_RUN | The earlier install was version 0.1.0; the 1.1.0 contracts change the CLI surface, so a fresh install must be observed before this can pass |

Runtime and installation observations are recorded separately in
[`runtime.md`](runtime.md).

## What is deliberately not claimed

- The four Skill descriptions were originally written as YAML block scalars, which the
  Skill loader reads as the single character `>` and which would have left every Skill
  unable to trigger. They are single-line values now, and the check that missed this has
  been replaced with one that parses frontmatter exactly as the consumer does: first
  colon wins, no block-scalar support. A test more permissive than production proves
  nothing about production.
- The TRACE scores above are below the 4.5 mark used elsewhere in this organisation. The
  remaining points are concentrated in the reference-tree and example-count sub-items.
  Closing them would mean adding reference files and example sets whose value here would
  be mostly the score itself, so they are reported as-is rather than padded.
- The real two-item run proves the observed happy path only. The tests exercise
  every failure classification using a fake generator; live timeout, missing
  artifact, and quota behavior remain unobserved.
- The image model used by the real run was not reported, and no document here
  infers one. Both receipts recorded `source.model_reported` as `null`.
- The usage-limit reset time is parsed from an event shape taken from the Codex
  source. It has not been observed from a live limit.
