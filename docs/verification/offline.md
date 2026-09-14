# Offline verification: 0.1.2 release candidate

These gates use no network, no account mutation, no plugin installation, and no
image allowance. The runtime remains Python 3.11+ standard-library-only.

## Commands

```bash
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -v
python3 scripts/validate_distribution.py .
git diff --check
```

The distribution validator also checks the presence and required commands of
the six-cell CI workflow. It does not replace execution on the three remote
operating systems.

## Coverage map

| Layer | Evidence |
| --- | --- |
| Closed schemas and migration | 1.0.0 plans/jobs migrate deterministically to 1.1.0 with strengthened approval and human-label policy. |
| Approval and execution | Approval binds the current plan hash, round, and remaining count; every external attempt is reserved first. |
| Concurrency and crashes | The cross-process job lock prevents a second writer; crash cases preserve `Attempting`/`Unknown` evidence without retry. |
| Receipt durability | Atomic per-item receipts are authoritative; the aggregate manifest is rebuildable. |
| Evaluation | A required missing human label prevents `pass`; model assessment remains advisory. |
| Recovery | Valid receipts reconcile state; ambiguous or tampered evidence is refused without invoking Codex. |
| Distribution | Manifest, marketplace, assets, pinned upstream snapshots, docs, CI contract, and secret scan are checked locally. |

## Local gate status

| Gate | Status | Evidence |
| --- | --- | --- |
| `compileall` | `PASS` | `python3 -m compileall -q scripts tests` exited 0 on 2026-09-14. |
| `full_source_tests` | `PASS` | 365 tests ran successfully on 2026-09-14. |
| `distribution_validation` | `PASS` | Validator reported compatibility foundation 0.1.2 and exited 0. |
| `git_diff_check` | `PASS` | `git diff --check` exited 0 on 2026-09-14. |

External and release gates are intentionally kept in
[`runtime.md`](runtime.md), where each one is explicitly `PASS`, `FAIL`, or
`NOT_RUN`. The currently available Codex CLI has no `plugin validate` command,
so this repository makes no such claim.
