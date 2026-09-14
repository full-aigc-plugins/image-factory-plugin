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

## Fix round 1/5

Renewed review found that the design's mutating-command rule had only been
applied to `evaluate` and `optimize`. The remediation extends canonical path
refusal to the first executable lines of `run` and `recover`.

### Added behavior

- `run` checks plan, job, destination, and explicitly supplied Codex home,
  generation directory, and binary paths before plan validation, capability
  probing, ledger creation, or generation.
- `recover` checks plan, job, and destination before plan or ledger reads and
  before receipt or manifest access.
- Exact, relative, and symlink spellings are covered. Regression tests prove
  refusals preserve all existing bytes, create no ledger/output/invocation
  evidence, and leave the source ledger in `Running` when applicable.
- `ALLOWED_TRANSITIONS` and `record_evaluation` now explicitly document their
  legacy compatibility role and require production evaluation to use the
  one-write `record_evaluation_final` path.

### RED evidence

```text
python3 -m unittest \
  tests.test_cli.RunCommandTests.test_run_refuses_path_collisions_before_probe_or_mutation \
  tests.test_recovery.RecoveryCommandTests.test_recover_refuses_exact_relative_and_symlink_aliases_without_mutation \
  -v
FAILED (failures=2, errors=3)
```

The old `run` reached the injected capability-probe failure, while old
`recover` tried to parse the aliased plan/destination as a ledger.

### GREEN and renewed verification evidence

```text
focused alias regression: Ran 2 tests ... OK
python3 -m unittest tests.test_cli tests.test_recovery tests.test_ledger -v
Ran 130 tests ... OK
python3 -m unittest discover -s tests -v
Ran 375 tests ... OK
python3 -m compileall -q scripts tests
exit 0
python3 scripts/validate_distribution.py .
validated codex-image-factory compatibility foundation 0.1.2
git diff --check
exit 0
```

No push, tag, installation, canary, or progress-ledger edit was performed.

## Fix round 2/5

The second review found two remaining preflight gaps: default `run` paths were
not included unless their flags were explicit, and handler-level validation ran
after `JobLock` had already created its sidecar.

### Added behavior

- A shared `mutating_command_paths`/`preflight_mutating_command_paths` path is
  now invoked by `run_cli` before lock acquisition and again at every mutating
  handler entry.
- `run` resolves and caches the effective Codex home, generation directory, and
  Codex binary even when all three CLI flags are omitted. The same values are
  reused by execution rather than resolved a second time.
- `recover`, `evaluate`, and `optimize` retain their complete role sets through
  the shared preflight.
- Collision refusal now creates no lock sidecar. Existing lock contention and
  serialization tests remain green for non-colliding commands.

### RED evidence

The three new/strengthened behavior tests produced eight expected failures:
the exact run/recover cases created lock sidecars, and omitted-default cases
reached capability probing instead of refusing their effective aliases.

### GREEN and renewed verification evidence

```text
lock-before-side-effect and default-path regression: Ran 3 tests ... OK
python3 -m unittest tests.test_cli tests.test_recovery tests.test_ledger -v
Ran 131 tests ... OK
python3 -m unittest discover -s tests -v
Ran 376 tests ... OK
python3 -m compileall -q scripts tests
exit 0
python3 scripts/validate_distribution.py .
validated codex-image-factory compatibility foundation 0.1.2
git diff --check
exit 0
```

No push, tag, installation, canary, or progress-ledger edit was performed.
