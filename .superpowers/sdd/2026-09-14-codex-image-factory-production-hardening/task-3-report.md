# Task 3 Report: Atomic JSON and Per-Item Receipts

## Status

Implemented the approved Task 3 scope. Durable JSON writes now share one atomic
writer, each collected artifact receipt is persisted independently before the
ledger records the item as generated, the aggregate manifest is rebuilt at the
end of a run, and evaluation loads only schema-valid receipts whose artifact
bytes, hash, and dimensions verify on disk.

## TDD evidence

- RED: `python3 -m unittest tests.test_atomic_json tests.test_receipt_store -v`
  failed with `ModuleNotFoundError` for `atomic_json` and `receipt_store`.
- GREEN: the same command passed 8 tests after the minimal implementation.
- Focused regression: `python3 -m unittest tests.test_atomic_json tests.test_receipt_store tests.test_ledger tests.test_cli -v`
  passed 66 tests.
- Full suite: `python3 -m unittest discover -s tests -v` passed 276 tests.
- Compile check: `python3 -m py_compile scripts/atomic_json.py scripts/receipt_store.py scripts/job_ledger.py scripts/image_factory_cli.py` exited successfully.
- Patch hygiene: `git diff --check` exited successfully.

## Implementation notes

- `write_json_atomic` uses a same-directory `.atomic-*.tmp`, sorted indented
  JSON with one trailing newline, file flush/fsync, atomic replace, best-effort
  parent-directory fsync, and exception cleanup.
- Receipt documents are validated against the closed artifact receipt schema.
- Receipt loads require deterministic filenames, unique idempotency keys,
  destination-contained artifact paths, and successful collector verification.
- Existing end-of-run manifest timing is intentionally retained for Task 6.

## Concerns

No known Task 3 defects. Crash reconciliation and changes to manifest timing are
deliberately deferred to Task 6 per the binding ruling.

## Review fix 1: Legacy aggregate compatibility

The first review found that rebuilding exclusively from the new per-item store
could erase earlier receipts held only in a legacy aggregate manifest when a
resumed job generated another pending item.

- RED: `python3 -m unittest tests.test_cli.RunCommandTests.test_resumed_legacy_manifest_keeps_prior_receipts_when_one_item_is_added -v`
  failed because the rebuilt item list was `['item-03']` instead of
  `['item-01', 'item-02', 'item-03']`.
- GREEN: after loading and verifying legacy aggregate entries before merging
  per-item receipts, the same real CLI regression passed.
- Focused regression: `python3 -m unittest tests.test_receipt_store tests.test_cli -v`
  passed 29 tests.
- Full suite: `python3 -m unittest discover -s tests -v` passed 278 tests.

During this compatibility phase, legacy entries retain append order and must
pass the same closed-schema, destination containment, artifact hash, byte-count,
and dimension checks as per-item receipts. Identical evidence present in both
stores is coalesced; conflicting or duplicate legacy idempotency keys are
refused. Task 6 crash reconciliation remains deferred.
