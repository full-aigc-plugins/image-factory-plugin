# Task 12 Report: Current-round evaluation cardinality and recovery acceptance

Date: 2026-09-14
Recorded base: `a5a32d65131ca562d51a59d968ab588d44d2059a`

## Scope delivered

- Added `current_rows_by_key(payload, current_keys)` and made evaluation reject a
  second ledger row for a current-plan idempotency key before receipt evidence is
  loaded or scores are written.
- Kept ledger rows with historical idempotency keys stored and excluded from the
  current-round cardinality check.
- Reused the same helper in `status` without changing its summary shape.
- Extended both recoverable round-two crash cases through real recovery, verified
  current-round receipt selection, human approval, real evaluation, round-two
  scores, and the final `Accepted` ledger state.
- Refreshed the documented offline full-suite count from 364 to 365.

## RED to GREEN evidence

The focused command was first run after adding the tests and before changing
production code. It ran three tests: the two extended crash-recovery acceptance
tests passed, while
`test_evaluate_refuses_duplicate_current_round_ledger_rows` failed because the
existing dictionary construction silently selected the contradictory duplicate
and reported `current receipt and ledger evidence do not match plan item
'item-01'` instead of rejecting duplicate current-round rows.

After the minimal helper and call-site change, the same focused command passed
all three tests.

## Verification evidence

- Focused Task 12 tests: 3 tests, `OK`.
- `python3 -m unittest tests.test_cli tests.test_multi_round_lifecycle -v`:
  58 tests, `OK`.
- `python3 -m unittest discover -s tests -v`: 365 tests, `OK`.
- `python3 -m compileall -q scripts tests`: exit 0.
- `python3 scripts/validate_distribution.py .`: reported
  `validated codex-image-factory compatibility foundation 0.1.2`, exit 0.
- `git diff --check`: exit 0.

## Self-review

Task-level verdict: approved. The new test preserves both pre-existing output
files across refusal, includes an out-of-round historical ledger row, and uses a
contradictory duplicate current row. Both lifecycle tests exercise the real CLI
evaluation handler, receipt loader, scores persistence, and ledger transitions;
they do not mock evaluation or recovery evidence.

Whole-branch local verdict: **Ready for candidate push: Yes**, subject to the
binding design's already-declared external release gates. No Critical or
Important source-quality finding was identified in the Task 12 diff. This task
did not push, tag, install, run a paid canary, alter SDD progress, or change any
external gate status.

## Remaining concerns

- Remote CI matrix, remote SHA parity, fresh Marketplace installation,
  fresh-session no-spend smoke, and paid canary remain separate external gates;
  this local task supplies no new evidence for them.
