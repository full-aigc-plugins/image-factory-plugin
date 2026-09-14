# Task 13 report: transaction path safety and atomic evaluation finalization

## Final status

PASS for the independent Task 13 implementation and local verification scope.
No push, tag, installation, Marketplace action, or paid canary was performed.

## Implemented

- Added canonical path comparison using expanded, absolute, non-strict resolved
  paths.
- `evaluate` rejects collisions among job, plan, scores, destination, labels,
  and advisory roles before reading optional inputs or publishing scores.
- `optimize` rejects collisions among job, plan, scores, output, destination,
  and rewrites roles before reading rewrites or publishing an optimized plan.
- Collision refusal returns structured JSON with `EXIT_USAGE` and leaves every
  participating path byte-identical.
- Added `record_evaluation_final`, mapping `fail`, `pass`, and
  `pending_approval` directly to `Evaluated`, `Accepted`, and
  `PendingApproval` in one history entry, revision, and atomic ledger write.
- Production evaluation now publishes scores atomically and performs only the
  single final ledger mutation. A simulated interruption between those writes
  leaves the source `Completed` ledger rerunnable.
- Preserved the duplicate-current-round and recovery-to-evaluation coverage
  introduced by Task 12; the complete source suite remains green.

## RED evidence

Before production changes, the focused command failed as expected:

```text
python3 -m unittest tests.test_cli.EvaluateAndOptimizeCommandTests tests.test_ledger -v
FAILED (failures=9, errors=7)
```

The failures demonstrated destructive file aliasing, directory collisions
reported with the wrong exit class, missing canonical symlink/relative alias
handling, and the absent one-write finalization API.

## GREEN and verification evidence

```text
python3 -m unittest tests.test_cli.EvaluateAndOptimizeCommandTests tests.test_ledger -v
Ran 84 tests ... OK

python3 -m unittest tests.test_cli tests.test_ledger -v
Ran 115 tests ... OK

python3 -m unittest discover -s tests -v
Ran 373 tests ... OK

python3 -m compileall -q scripts tests
exit 0

python3 scripts/validate_distribution.py .
validated codex-image-factory compatibility foundation 0.1.2

git diff --check
exit 0
```

## Self-review

- The collision guard runs inside the existing exact job lock and before any
  command data mutation.
- The helper uses the binding design's `resolve(strict=False)` behavior, so it
  also covers prospective outputs and symlinked parents.
- Compatibility `record_evaluation` remains for existing callers and tests;
  the production evaluate path exclusively uses `record_evaluation_final`.
- The design state diagram now shows direct evaluation outcomes rather than a
  pass/pending intermediate `Evaluated` state.

## Commit

Commit message: `fix: protect Image Factory transaction paths`.
The resulting commit SHA is reported by the task owner after commit creation.

## Remaining concerns

- Symlink behavior is exercised on this macOS host and conditionally skipped on
  hosts that cannot create directory symlinks; remote CI remains responsible
  for the supported OS matrix.
- This task does not renew the whole-branch review or authorize candidate push.
