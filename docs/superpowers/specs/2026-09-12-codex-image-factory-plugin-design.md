# Codex Image Factory Plugin Design Specification

> Status: implemented. Version 0.1.0. 2026-09-12.

## Goal

Make producing a batch of images a reproducible, auditable, resumable operation
inside Codex: validate a plan, quote it, generate with explicit approval, collect
a hash-verified receipt for every artifact, evaluate against deterministic gates,
and turn the failures into a new round whose prompts the user can inspect.

## Requirements

1. A batch is described by a closed JSON document; unknown fields are refused.
2. Validation, quoting, and generation are separate steps, and only generation
   spends the account's image allowance.
3. A plan that requires approval cannot run without an explicit approval flag.
4. An item is complete only when a new image file exists and its hash, byte
   count, and dimensions are recomputed from disk.
5. Identical content standing in for two different items is reported for every
   participant rather than silently accepted.
6. Job state is durable, written atomically, and permits only the transitions the
   ledger declares.
7. A ledger never holds a credential-like key, on read or on write.
8. A resumed run does not regenerate an item that already has a receipt, and does
   not retry an item that already failed.
9. Deterministic checks decide pass or fail. A model-authored score is recorded
   as advisory and can at most request a human.
10. A human rejection fails the batch regardless of any other signal.
11. Optimisation writes a new round document and never edits the previous one.
12. Reaching the round ceiling is reported as incomplete, never as success.
13. No component installs software, bypasses approvals, or retries automatically.
14. The plugin never reads, copies, or stores authentication material.
15. Every declared contract is expressed as JSON Schema, and the enforcement code
    is driven by those schemas rather than by parallel rules.

## Non-goals

- Generating a single image on request.
- Controlling size, quality, background, or image count: the built-in tool does
  not expose them, so the plugin does not pretend to.
- Selecting, naming, or promising an image model.
- Reading an API key, or shipping an API channel of its own.
- Editing or compositing an existing image in place.
- Running as a service, a daemon, or an MCP server.
- Automatic publish: a batch ends with a decision, not with a release.

## Acceptance

- `python3 -m unittest discover -s tests -v` passes, including RED-first coverage
  of every failure classification.
- `python3 scripts/validate_distribution.py .` prints
  `validated codex-image-factory compatibility foundation 0.1.0`.
- The official plugin validator accepts the repository.
- `bin/image-factory probe` reports an actionable verdict on a machine where
  generation is not available, and reports `available` where it is.
- A batch plan whose items request a size or a quality tier is rejected, and no
  ledger is written for it.
- A run without `--approve` on a plan that requires approval exits with the
  approval code, records `approval_required`, and generates nothing.
- A usage limit stops the run, is recorded with its reset time, and does not
  attempt the remaining items.
- A runtime generation run against a real Codex account is **not** part of
  acceptance for this version, and is recorded as an open item in
  `docs/verification/offline.md` rather than being claimed as verified.
