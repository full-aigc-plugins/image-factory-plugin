# Final review fix wave

## Status

All assigned final-review findings are fixed in the local hardening worktree.
No push, tag, installation, paid canary, or SDD progress mutation was performed.

## Fixes

- Preserved append-only historical ledger rows while binding current-round status,
  recovery, resume safety, and counts to the current plan's idempotency keys.
- Changed attempt completion lookup to use the unique `attempt_id`, so a reused
  item id in a later round cannot resolve to an earlier row.
- Made evaluation require exactly the current key's verified receipt and check
  batch id, round, item id, prompt hash, generated ledger state, and ledger
  receipt id before writing scores.
- Scoped receipt loading for recovery and evaluation to current-round keys so
  stale receipts cannot mask missing or tampered current evidence.
- Added a persisted current-key binding used by status, including rejection of
  duplicate current-round rows instead of emitting non-conserving counts.
- Rejected zero, negative, NaN, and infinite generation timeouts at argument
  parsing time, before a job is written or generation is invoked.
- Refreshed offline evidence to plugin version 0.1.2 and 364 tests.

## TDD evidence

The initial focused run failed on all intended defects: round-two completion
resolved the old item row, recovery rejected historical rows, status counted
historical rows, stale receipt selection remained possible, and invalid timeouts
entered execution. A separate RED test demonstrated that duplicate current rows
could overcount the bound total. Each focused set passed after the minimal fixes.

## Final verification

```text
python3 -m unittest discover -s tests -v
Ran 364 tests in 8.869s — OK

python3 -m compileall -q scripts tests
exit 0

python3 scripts/validate_distribution.py .
validated image-factory compatibility foundation 0.1.2

git diff --check
exit 0
```

The lifecycle coverage now performs round 1 generation, evaluation, rejection,
and optimization; round 2 generation and evaluation; and round 2 recovery at
the pre-attempt, post-invocation, post-publication, post-receipt, and
post-ledger-completion durability boundaries. It also proves stale round 1
receipts cannot mask missing or mismatched round 2 evidence.

## Self-review and remaining concerns

Manual review found no remaining in-scope correctness, security, or compatibility
finding. Historical receipts and ledger rows remain durable; only current-round
decision projections are filtered. The existing external release gates remain
out of scope and `NOT_RUN`. Independent delegated review is unavailable because
this fix wave explicitly prohibited subagent dispatch; this report therefore
records manual self-review and deterministic test evidence, not an independent
merge approval.
