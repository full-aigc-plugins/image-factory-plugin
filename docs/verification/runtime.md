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
| `remote_ci_matrix` | `NOT_RUN` | No 0.1.2 candidate has been pushed; all six remote jobs remain unobserved. |
| `remote_sha_parity` | `NOT_RUN` | Local, tracking, remote-main, and tag parity is a Task 11 publication gate. |
| `fresh_marketplace_install` | `NOT_RUN` | Removing or installing a plugin requires separate authorization. |
| `fresh_session_no_spend_smoke` | `NOT_RUN` | It must target a freshly installed 0.1.2 candidate. |
| `paid_canary` | `NOT_RUN` | No allowance-spending run is authorized by Task 10. |
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
