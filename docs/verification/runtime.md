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
| `remote_sha_parity` | `PASS` | `main` is at `05674dc` locally and on `origin`. Tag parity is not yet claimed: it requires the `v0.1.2` tag, which the release step adds. |
| `fresh_marketplace_install` | `PASS` | The `partme-ai-image-factory` snapshot was upgraded, the plugin removed, and `codex plugin add codex-image-factory@partme-ai-image-factory` reinstalled 0.1.2. All 188 version-controlled files in the cache are byte-identical to the pushed commit. |
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
