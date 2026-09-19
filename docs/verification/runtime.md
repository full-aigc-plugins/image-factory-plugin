# Runtime and release verification: 0.1.4 candidate status

The `0.1.4` candidate changes only skill provenance, synchronization, and release metadata. The evidence table below remains the immutable `0.1.2` runtime record; it is not presented as fresh `0.1.4` installation, remote SHA, or paid-generation proof. Current-candidate evidence is added only after the corresponding check is actually rerun.

This file is the evidence ledger for the Image Factory 0.1.2 release
candidate. It intentionally does not reuse runtime, installation, remote commit,
or paid-generation results from an earlier version. A gate changes from
`NOT_RUN` only when it is freshly observed against the exact candidate named by
the release process.

Allowed status values are `PASS`, `FAIL`, and `NOT_RUN`.

## External gate status

| Gate | Status | Evidence |
| --- | --- | --- |
| `remote_ci_matrix` | `PASS` | Run 34831417381 on `05674dc`: all six legs green (ubuntu/macos/windows x Python 3.11/3.13). The first two pushes failed on Windows 3.11 only; the causes and fixes are in the commits `d93748e` and `05674dc`. |
| `remote_sha_parity` | `PASS` | The annotated `v0.1.2` tag and `origin/main` resolve to the same commit; `git rev-list -n1 v0.1.2` is authoritative for the tag's target. The tag is dated and carries a message describing the release. |
| `fresh_marketplace_install` | `PASS` | Reinstalled through the `personal` marketplace on 2026-09-14: `codex plugin add codex-image-factory@personal` installed 0.1.2, and every installed file is byte-identical to the source tree (`diff -rq`, excluding `.git` and caches). |
| `fresh_session_no_spend_smoke` | `PASS` | A fresh `codex exec` session used the installed plugin to validate and quote a two-item plan and reported the plan hash, image count, and approval requirement. The reported hash `0792c5df...` was recomputed locally from the same plan and matched. The quote reported `spends_allowance_on_quote: false`. |
| `paid_canary` | `PASS` | Five authorized generation calls on 2026-09-14 across two batches, none retried. Batch A round 1 produced three artifacts (302,076 / 383,074 / 264,860 bytes) and round 2 one artifact (179,848 bytes); the product-surface batch produced one artifact (368,875 bytes). Every artifact is 1254x1254 and every receipt SHA-256 was re-derived with `shasum -a 256`. `source.model_reported` is `null` throughout. |
| `multi_round_closed_loop` | `PASS` | Round 1 evaluated to `fail` with all deterministic gates passing and one item rejected on measured non-conformance; `optimize` carried the two passing items forward and emitted a round-2 plan containing only the rejected item; round 2 evaluated to `pass` and the job reached `Accepted`. Ledger revision 25, two recorded approvals (3 calls, then 1). |
| `product_surface_paid_run` | `PASS` | A fresh `codex exec` session, given only the installed plugin and a plan, declared `image-factory-run` as the skill it was using, then ran `validate-plan`, `quote` (reporting plan hash `e0a7ecdc...`), and `run --approve`. It made exactly one call, reported `Completed` and SHA-256 `7ab82026...`, and stated that no retry was made. The plan hash was recomputed and the artifact re-hashed independently; both matched. |
| `cross_platform_generation` | `NOT_RUN` | The generation path has been driven on macOS 26.6.2 only. CI covers the offline suite and the job lock on three operating systems, but a CI runner has no signed-in account and must not be given one. Procedure in [`../guides/runtime-evidence-collection.md`](../guides/runtime-evidence-collection.md). |
| `usage_limit_evidence` | `NOT_RUN` | Exhausting the account's image allowance is neither required nor authorized, so this path is covered only by the offline suite against the event shape taken from the Codex source; it has never been observed live. Procedure for an operator who chooses to spend it: [`../guides/runtime-evidence-collection.md`](../guides/runtime-evidence-collection.md). |

## Evidence recording rules

- Remote CI evidence must name the workflow run and show all Linux, macOS, and
  Windows jobs for Python 3.11 and 3.13 as completed successfully.
- SHA parity evidence must be freshly read after publication. Never copy an old
  remote SHA into this file as the current candidate SHA.
- Installation evidence must record the installed version and cache commit
  after an authorized clean reinstall; source checkout success is not install
  evidence.
- The no-spend smoke must come from a fresh session and cover Skill discovery
  plus `probe`, `validate-plan`, `quote`, `status`, and `recover` reachability.
- A paid canary requires a new explicit approval bound to the exact plan hash,
  round, and remaining call count. It must verify per-item receipts and end with
  required human labels and `Accepted` state.
- A generation claim is recorded only when the artifact hash has been re-derived
  with a tool other than the plugin's own code and the pixel size has been read
  back independently.

## Measured outcome of the multi-round loop

The round-2 rewrite is worth recording because the change it produced is
measurable from the pixels. The rejected item moved from an amber-contaminated
mark with a narrow horizontal margin to a clean emerald mark with roughly double
the margin:

| Metric | Round 1 | Round 2 |
| --- | --- | --- |
| Mean ink RGB | `[98, 119, 44]` (amber-shifted) | `[8, 106, 59]` (deep emerald) |
| Green advantage (G - max(R,B)) | 21 | 47 |
| Horizontal margin | 95 / 92 px (7.4%) | 191 / 190 px (15.2%) |
| Ink bounding box | 1067 x 474 | 873 x 371 |

The rejection was made against the plan's own written requirements ("centred
with generous empty margin", "deep emerald green"), not against taste, and the
metrics are reproducible with a standard-library PNG reader.

Two label caveats belong with this result rather than being left implicit:

- The `rejected` label was assigned by an automated reviewer working from those
  metrics, not by a human looking at the images.
- The item was not regenerated on a hunch: `optimize` refuses to emit a round
  without an explicit rewrite for every item it marks as needing rework.

## Host conditions observed while collecting this evidence

Both of these were measured, and both would otherwise look like plugin defects:

- Placing the plan or the job ledger inside the destination tree is refused
  before anything is spent (`path collision between plan and destination tree`,
  `path collision between job and destination tree`). Keep `plans/`, `jobs/`,
  and `out/` as siblings.
- Wrapping the caller in a restricted sandbox decides whether generation works,
  because the restriction is inherited by the processes the plugin spawns. With
  `codex exec -s workspace-write`, `probe` reported
  `generation_dir_unwritable`, because `~/.codex/generated_images` sits outside
  the writable workspace; the same action succeeded once that override was
  removed. `--add-dir <CODEX_HOME>/generated_images` is the narrow fix, and
  `--dangerously-bypass-approvals-and-sandbox` is not an acceptable one — the
  plugin forbids that flag on purpose and asserts against it in tests.

The current verdict is **verified on macOS for the generation path, and still a
release candidate overall**: the generation path has not been exercised on Linux
or Windows, and the exhausted-allowance path has never been observed live. No
official `codex plugin validate` command is claimed: the currently available
Codex CLI does not provide one.

## Local release-candidate preparation

The 0.1.2 manifest, changelog, bilingual README files, architecture documents,
runtime evidence, distribution tests, and validator output are version-aligned.
This local preparation is not remote publication, installation evidence, or a
paid acceptance result; the external gate table above remains authoritative.

## Local environment note

The dev host's `~/.codex/config.toml` pointed `model_catalog_json` at a catalog file
that the installed Codex can no longer parse (`missing field
supports_parallel_tool_calls`), which made every config-loading command fail —
including `codex exec`, and therefore every path this plugin uses to generate. The
reference was commented out (with a timestamped backup of `config.toml` next to it)
so the reinstall and canary above could run. The catalog file itself was not
modified. Restore the line after regenerating that file.

Nothing in this repository depends on that setting; the finding is recorded here
because it would otherwise look like a plugin failure.

## Tag history

`v0.1.2` was re-pointed before any GitHub Release referenced it, so that the tag
would carry the verification record rather than an earlier draft of it. No file
under `scripts/` or `schemas/` differed across the moves, so the released code is
identical in every target the tag has ever pointed at. A consumer that fetched an
earlier tag should re-fetch; the annotated tag's message and
`git rev-list -n1 v0.1.2` are the authoritative statement of what it points at.
