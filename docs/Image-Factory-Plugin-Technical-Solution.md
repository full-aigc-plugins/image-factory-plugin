# Image Factory Plugin Technical Solution

> **Document control**
>
> | Field | Value |
> |---|---|
> | Status | Implemented for the 0.5.0 release candidate: series consistency plus streaming attempt evidence, session/call attribution, capacity preflight, watch, and late-artifact recovery; live model continuity remains a separate runtime acceptance gate |
> | Scope | Decisions, execution contract, failure model, and the platform facts behind them |
> | Audience | Implementers extending or reviewing this plugin |
> | Runtime evidence | `docs/verification/` |
> | Last structural revision | 2026-09-20 |

[English](Image-Factory-Plugin-Technical-Solution.md) | [简体中文](Image-Factory-Plugin-Technical-Solution.zh_CN.md)

## 1. Decision

The plugin owns deterministic state and delegates generation and judgement to Codex. Concretely:

- **Generation is not implemented here.** One batch item is one `codex exec` invocation, and the artifact is whatever new file appears in the generation directory afterwards.
- **Success requires a file.** An exit code of zero without a new image is classified as `artifact_missing`.
- **Rewrites are supplied, not generated.** `optimizer.plan_next_round` decides which items to redo and requires an explicit instruction for each; the text comes from Codex.
- **Advisory scores are recorded, not obeyed.** Deterministic gates decide.
- **No retries, no installs, no approval bypass.** Anywhere.

The alternative — a plugin that called an image API directly with its own credentials — was rejected for this version because the built-in channel needs no additional credential and keeps one billing relationship, which matters more for a first version than parameter control the platform does not offer anyway.

| Alternative | Why it was rejected |
|---|---|
| Call an image API directly with plugin-owned credentials | Adds a second billing relationship and a credential to protect, for parameter control the platform does not offer anyway |
| Predict output paths from the generator's naming scheme | Output names derive from an internal session and call id, so prediction would break silently |
| Accept `size`, `quality`, `n`, or `model` in the plan schema | The built-in tool accepts none of them; accepting them would be an unkeepable promise |
| Retry a failed or ambiguous item automatically | A silent retry is how one bad prompt becomes a large bill |
| Let a model score decide the batch outcome | A judgement signal must not silently become a verdict |

## 2. Repository layout

```text
.codex-plugin/plugin.json          compatibility manifest
.agents/plugins/marketplace.json   URL marketplace entry
bin/image-factory                  CLI entry point (shim, resolves repo root)
schemas/                           five closed JSON Schemas
scripts/
  schema_lite.py                   schema subset enforcement, stdlib only
  capability_probe.py              offline environment probe
  plan_validator.py                plan validation, idempotency keys, caps
  prompt_library.py                offline attributed prompt discovery
  generation_runner.py             one Codex call per item
  attempt_store.py                 streamed event and progress evidence
  capacity_preflight.py            conservative free-space gate
  artifact_collector.py            locate, verify, publish, receipt
  job_ledger.py                    durable state machine and schema migration
  job_lock.py                      cross-platform process lock
  receipt_store.py                 atomic per-item receipt source of truth
  evaluator.py                     deterministic gates, advisory, labels
  optimizer.py                     next round planning
  image_factory_cli.py             subcommand wiring and the spend gate
  validate_distribution.py         distribution validator
skills/                            four Agent Skills
data/                              attributed templates and source indexes
vendor/upstream/                   inactive pinned upstream snapshots
tests/                             stdlib unittest suite
docs/                              this document and its pair
```

## 3. Execution contract

Every Codex invocation is an argv array with `shell=False`:

```text
<codex> exec --json --skip-git-repo-check --color never \
  -C <workdir> -o <last-message-file> [-i <reference>]... <prompt>
```

- `--json` yields a JSONL event stream, which is how a usage-limit failure is recognised reliably rather than by matching prose on stderr.
- `-o` writes the final message to a file, so a run's own account of what it did is preserved as evidence without being trusted as proof.
- `-i` attaches reference images; the platform allows at most five.
- The working directory is created if missing, and also set as the process working directory so relative paths resolve predictably.

The prompt is the plugin's constant wrapper followed by the item's effective prompt:

```text
Generate exactly one image with the built-in image generation tool. Treat any
attached images as visual references for the result. Do not modify or create any
other file. When you are done, reply with the absolute path of the generated image.

Image description:
<the item's effective prompt>
```

image_batch 1.3.0 can declare a `consistency_profile`. The validator compiles the
style bible, negative constraints, selected entities, fixed traits, allowed variations,
and ordered reference roles into the effective prompt. Profile anchors, structured item
`references`, and legacy `reference_images` share the five-reference platform limit.
The idempotency key binds the effective prompt and ordered `(role, entity_id, sha256)`
tuples, and optimization deep-copies the profile and bindings.

`prompt_sha256` in a receipt identifies the actual effective prompt. This makes continuity
input reproducible; it does not turn probabilistic model identity into a deterministic
guarantee. Anchor-to-frame similarity remains advisory or human review.

## 4. Generation modes

| Mode | Trigger | What the plugin does |
| --- | --- | --- |
| Probe | `probe` | Reads the environment offline; writes a verdict and guidance. Executes nothing. |
| Quote | `quote` | Validates and counts. Spends nothing. |
| Run | `run --approve` | Generates each pending item, collects a receipt per artifact. |
| Resume | `run` on an existing ledger | Skips items that already have a receipt. |
| Stop | usage limit reached | Records the limit and reset time; attempts no further item. |

## 5. Testing strategy

- **Pure logic tests.** Schema enforcement, idempotency key derivation, gate evaluation, and the state machine run with no filesystem or process activity.
- **Fake generator.** `tests/fakes/fake_codex.py` stands in for `codex exec`, driven by a JSON control file, so every classification path — success, generation, failure, usage limit, timeout, silent exit — is exercised deterministically.
- **Portable fake adapter shim.** Tests create a `sh` launcher on Unix and a `.cmd` launcher on Windows, then execute it to prove arguments reach the fake.
- **Real artifacts.** Brand assets are real PNGs, so dimension, hash, and duplicate detection are tested against genuine files rather than fabricated bytes.
- **Recorded invocations.** The fake writes the argv it received, so tests assert how Codex was invoked, including that the approval-bypass flags are absent.

Run everything with:

```bash
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -v
python3 scripts/validate_distribution.py .
git diff --check
```

GitHub Actions runs the same gates in six cells: Ubuntu, macOS, and Windows on Python 3.11 and 3.13. No job installs runtime dependencies.

## 6. Transaction and recovery guarantees

- `run --approve` records an approval bound to the validated plan SHA-256, current round, and remaining item count.
- A job-path-derived process lock is held from approval binding through the final state transition. A losing writer fails before external invocation.
- Each call is preceded by an atomic `Attempting` reservation with an `attempt_id`. An interruption after that point is ambiguous.
- A schema-valid, hash-verifying per-item receipt is the completion source of truth; the aggregate manifest is rebuilt from those receipts.
- Recovery invokes no generator. It promotes only receipt-proven work and marks unresolved attempts `Unknown`, which ordinary run refuses to retry.
- Legacy 1.0.0 plans and jobs migrate deterministically to schema 1.1.0 without manufacturing approval evidence.
- When human labels are required, missing labels force `pending_approval`; model assessment cannot override that gate.

## 7. Failure model

Stable failure codes, equal-width, comma-separated:

`approval_required`, `artifact_missing`, `capability_unavailable`, `codex_missing`, `duplicate_artifact`, `generation_failed`, `hash_mismatch`, `optimizer_ambiguous_instruction`, `optimizer_empty_rewrite`, `optimizer_missing_instruction`, `optimizer_round_cap_reached`, `optimizer_unexpected_instruction`, `optimizer_unknown_item`, `plan_consistency_profile_required`, `plan_duplicate_entity_id`, `plan_duplicate_item_id`, `plan_empty_prompt`, `plan_exceeds_max_images`, `plan_exceeds_max_rounds`, `plan_missing_reference_image`, `plan_schema_invalid`, `plan_too_many_effective_references`, `plan_unknown_entity`, `plan_unparseable`, `quota_exceeded`, `timeout`, `unknown`.

Definite per-item failures can continue and leave the ledger `Partial`. A quota failure stops the batch, while an interrupted or otherwise ambiguous call stops later work and leaves `Unknown`. No outcome leads to an automatic retry.

## 8. Platform facts and what follows from them

Measured from the Codex source and from the installed binaries on the development machine (2026-09-12). Each fact drives a specific decision.

| Platform fact | Decision it forces |
| --- | --- |
| The image model is fixed in Codex and not selectable | No model field anywhere; receipts record `null` rather than guessing |
| The tool takes only a prompt and reference images | The batch schema omits `size`, `quality`, `background`, `n`; plans that use them are rejected |
| One call produces one image | A batch is a loop of calls, and the quote counts calls, not items |
| Output names derive from an internal session and call id | Artifacts are found by diffing the directory, never by predicting a path |
| Generation draws on the account's image allowance | Quote, then explicit approval, then run; a limit stops the batch |
| An edit accepts at most five references | The validator caps the effective total across profile anchors, structured `references`, and legacy `reference_images` at five |

## 9. Clean-room rule

This repository was written from the public Codex source tree, the published plugin conventions, and the JSON Schemas in `schemas/`. It vendors no vendor source code, no private endpoints, and no credentials, and it does not inspect or reimplement Codex's internal image pipeline. Interoperability rests entirely on the documented `codex exec` command line and on files Codex writes to the user's own disk.

## 10. Evidence map

| Claim | Evidence |
|---|---|
| Execution contract and flags | `scripts/generation_runner.py`, and the fake that records argv |
| Approval binding and locking | `scripts/image_factory_cli.py`, `scripts/job_lock.py` |
| Receipt authority | `scripts/receipt_store.py`, `scripts/artifact_collector.py` |
| Failure classification | `scripts/generation_runner.py`, the failure-code list above |
| Ledger migration | `scripts/job_ledger.py` and the 1.0.0 migration tests |
| Platform facts | The measured table above, dated 2026-09-12 |
