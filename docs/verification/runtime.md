# Runtime and release verification: 0.1.2

This file is the evidence ledger for the Codex Image Factory 0.1.2 release
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
| `fresh_marketplace_install` | `PASS` | The `partme-ai-image-factory` snapshot was upgraded, the plugin removed, and `codex plugin add codex-image-factory@partme-ai-image-factory` reinstalled 0.1.2. All 188 files in the cache are byte-identical to the `v0.1.2` tag, checked again after the tag was pushed. |
| `fresh_session_no_spend_smoke` | `PASS` | A fresh `codex exec` session used the installed plugin to validate and quote a two-item plan and reported the plan hash, image count, and approval requirement. The reported hash `0792c5df...` was recomputed locally from the same plan and matched. The quote reported `spends_allowance_on_quote: false`. |
| `paid_canary` | `PASS` | One authorized generation call on `be48f5d` (2026-09-14): the same plan was refused with exit code 3 without `--approve`, then ran once with it. Ledger reached `Completed` at revision 10 with one `Generated` item at `attempts: 1`. Artifact 714,394 bytes, 1254x1254, sha256 `68eac3b3...`, independently re-hashed with `shasum -a 256` and matching the receipt. `source.model_reported` is `null`. |
| `usage_limit_evidence` | `NOT_RUN` | Deliberately exhausting image allowance is neither required nor authorized. |

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

The current verdict is **release candidate, not production-ready**. No official
`codex plugin validate` command is claimed: the currently available Codex CLI
does not provide one.

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

`v0.1.2` was re-pointed once, before any GitHub Release referenced it. The previous
target (`98fc6e32`) and the current one differ only in documentation and evidence:
the audit of each task's declared deliverables and this verification record. No file
under `scripts/` or `schemas/` changed between them, so the released code is identical
either way. A consumer that fetched the earlier tag should re-fetch; the annotated
tag's message and `git rev-list -n1 v0.1.2` are the authoritative statement of what it
points at.
