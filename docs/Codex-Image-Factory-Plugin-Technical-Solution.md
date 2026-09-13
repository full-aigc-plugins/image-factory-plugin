# Codex Image Factory Plugin Technical Solution

> Implemented technical proposal for version 0.1.1. Updated 2026-09-13. Describes what the code does today, not what it might do.

[English](Codex-Image-Factory-Plugin-Technical-Solution.md) | [简体中文](Codex-Image-Factory-Plugin-Technical-Solution.zh_CN.md)

## 1. Decision

The plugin owns deterministic state and delegates generation and judgement to
Codex. Concretely:

- **Generation is not implemented here.** One batch item is one `codex exec`
  invocation, and the artifact is whatever new file appears in the generation
  directory afterwards.
- **Success requires a file.** An exit code of zero without a new image is
  classified as `artifact_missing`.
- **Rewrites are supplied, not generated.** `optimizer.plan_next_round` decides
  which items to redo and requires an explicit instruction for each; the text
  comes from Codex.
- **Advisory scores are recorded, not obeyed.** Deterministic gates decide.
- **No retries, no installs, no approval bypass.** Anywhere.

The alternative — a plugin that called an image API directly with its own
credentials — was rejected for this version because the built-in channel needs no
additional credential and keeps one billing relationship, which matters more for
a first version than parameter control the platform does not offer anyway.

## 2. Repository layout

```text
.codex-plugin/plugin.json          compatibility manifest
.agents/plugins/marketplace.json   URL marketplace entry
bin/image-factory                  CLI entry point (shim, resolves repo root)
schemas/                           four closed JSON Schemas
scripts/
  schema_lite.py                   schema subset enforcement, stdlib only
  capability_probe.py              offline environment probe
  plan_validator.py                plan validation, idempotency keys, caps
  prompt_library.py                offline attributed prompt discovery
  generation_runner.py             one Codex call per item
  artifact_collector.py            locate, verify, publish, receipt
  job_ledger.py                    durable state machine
  evaluator.py                     deterministic gates, advisory, labels
  optimizer.py                     next round planning
  image_factory_cli.py             subcommand wiring and the spend gate
  validate_distribution.py         distribution validator
skills/                            four Agent Skills
data/                              attributed templates and source indexes
vendor/upstream/                   inactive pinned upstream snapshots
tests/                             238 tests, stdlib unittest
docs/                              this document and its pair
```

## 3. Execution contract

Every Codex invocation is an argv array with `shell=False`:

```text
<codex> exec --json --skip-git-repo-check --color never \
  -C <workdir> -o <last-message-file> [-i <reference>]... <prompt>
```

- `--json` yields a JSONL event stream, which is how a usage-limit failure is
  recognised reliably rather than by matching prose on stderr.
- `-o` writes the final message to a file, so a run's own account of what it did
  is preserved as evidence without being trusted as proof.
- `-i` attaches reference images; the platform allows at most five.
- The working directory is created if missing, and also set as the process
  working directory so relative paths resolve predictably.

The prompt is the plugin's constant wrapper followed by the item's prompt:

```text
Generate exactly one image with the built-in image generation tool. Treat any
attached images as visual references for the result. Do not modify or create any
other file. When you are done, reply with the absolute path of the generated image.

Image description:
<the item's prompt>
```

The wrapper is constant so the author's prompt is the only variable part of a
request, and `prompt_sha256` in a receipt therefore identifies exactly what was
asked for.

## 4. Generation modes

| Mode | Trigger | What the plugin does |
| --- | --- | --- |
| Probe | `probe` | Reads the environment offline; writes a verdict and guidance. Executes nothing. |
| Quote | `quote` | Validates and counts. Spends nothing. |
| Run | `run --approve` | Generates each pending item, collects a receipt per artifact. |
| Resume | `run` on an existing ledger | Skips items that already have a receipt. |
| Stop | usage limit reached | Records the limit and reset time; attempts no further item. |

## 5. Testing strategy

- **Pure logic tests.** Schema enforcement, idempotency key derivation, gate
  evaluation, and the state machine run with no filesystem or process activity.
- **Fake generator.** `tests/fakes/fake_codex.py` stands in for `codex exec`,
  driven by a JSON control file, so every classification path — success,
  generation, failure, usage limit, timeout, silent exit — is exercised
  deterministically.
- **Fake adapter shim.** A one-line `sh` shim makes the fake an executable, one
  per test module because macOS evaluates a newly written executable on first
  run.
- **Real artifacts.** Brand assets are real PNGs, so dimension, hash, and
  duplicate detection are tested against genuine files rather than fabricated
  bytes.
- **Recorded invocations.** The fake writes the argv it received, so tests assert
  how Codex was invoked, including that the approval-bypass flags are absent.

Run everything with:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_distribution.py .
```

## 6. Failure model

Stable failure codes, equal-width, comma-separated:

`approval_required`, `artifact_missing`, `capability_unavailable`,
`codex_missing`, `duplicate_artifact`, `generation_failed`, `hash_mismatch`,
`optimizer_ambiguous_instruction`, `optimizer_empty_rewrite`,
`optimizer_missing_instruction`, `optimizer_round_cap_reached`,
`optimizer_unexpected_instruction`, `optimizer_unknown_item`, `plan_duplicate_item_id`,
`plan_empty_prompt`, `plan_exceeds_max_images`, `plan_exceeds_max_rounds`,
`plan_missing_reference_image`, `plan_schema_invalid`, `plan_unparseable`,
`quota_exceeded`, `timeout`, `unknown`.

Per-item failures never abort a batch; the run continues and the ledger ends in
`Partial`. A quota failure aborts the batch by design. No failure code leads to
an automatic retry of anything.

## 7. Platform facts and what follows from them

Measured from the Codex source and from the installed binaries on the development
machine (2026-09-12). Each fact drives a specific decision.

| Platform fact | Decision it forces |
| --- | --- |
| The image model is fixed in Codex and not selectable | No model field anywhere; receipts record `null` rather than guessing |
| The tool takes only a prompt and reference images | The batch schema omits `size`, `quality`, `background`, `n`; plans that use them are rejected |
| One call produces one image | A batch is a loop of calls, and the quote counts calls, not items |
| Output names derive from an internal session and call id | Artifacts are found by diffing the directory, never by predicting a path |
| Generation draws on the account's image allowance | Quote, then explicit approval, then run; a limit stops the batch |
| An edit accepts at most five references | The schema caps `reference_images` at five |

## 8. Clean-room rule

This repository was written from the public Codex source tree, the published
plugin conventions, and the JSON Schemas in `schemas/`. It vendors no vendor
source code, no private endpoints, and no credentials, and it does not inspect or
reimplement Codex's internal image pipeline. Interoperability rests entirely on
the documented `codex exec` command line and on files Codex writes to the
user's own disk.
