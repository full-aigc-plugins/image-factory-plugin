# Runtime verification

This document records the runtime checks performed on 2026-09-12. It keeps
observed evidence separate from checks that would spend image allowance or
change the local Codex installation.

## Capability probe

Command:

```bash
bin/image-factory probe --json
```

Observed verdict: `available` (exit code 0).

Observed fields:

```json
{
  "auth_present": true,
  "binary_source": "path",
  "configured_provider": "openai",
  "generation_dir_writable": true,
  "guidance": "",
  "image_generation_override": null,
  "model_reported": null,
  "reasons": ["verified_codex_binary"],
  "unverified": [
    "model_is_chosen_by_codex",
    "account_plan_type",
    "provider_capability_flags",
    "feature_default_enabled"
  ],
  "verdict": "available"
}
```

Local absolute paths and the configured text-model name are omitted from this
repository record. The command is filesystem-only and did not execute Codex or
make a generation call.

## Real two-item generation

Status: `PASS`.

The user approved a two-call verification batch. The plan was validated and
quoted before execution:

```text
batch_id: runtime-verification-20260912
round: 1
image_count: 2
approval_required: true
```

The approved run attempted each item exactly once, failed zero items, collected
two receipts, and ended with ledger state `Completed` at revision 7. The
follow-up deterministic evaluation reported `all_gates_passed: true` and
`decision: pass`.

| Item | Published file | Bytes | Dimensions | SHA-256 |
| --- | --- | ---: | ---: | --- |
| `emerald-circle` | `runtime-verification-20260912/round-1/emerald-circle-r1-74ff485743ac.png` | 847249 | 1254 x 1254 | `058adc202387e8bf5239257242d756e8c3bbe1a8e8b2732236d4d225c3fee66a` |
| `amber-triangle` | `runtime-verification-20260912/round-1/amber-triangle-r1-b894a0b9c2bf.png` | 680802 | 1254 x 1254 | `e8912a91ee1fa1497990032d23496838361966abd970584bb5a3bf4857302606` |

Independent `shasum -a 256` output matched both receipt hashes. Visual inspection
also confirmed that the files contain the requested green circle and amber
triangle on warm-white backgrounds.

Both receipts recorded `source.model_reported: null`; no model name is inferred.
The ledger recorded `usage_limit: null`, so no usage limit was encountered.

## Marketplace resolution and installation

Read-only resolution command:

```bash
git ls-remote --heads https://github.com/partme-ai/codex-image-factory-plugin.git main
```

Observed remote head:

```text
fff20c9aad9a9cd7893644306c752b2f7231071d refs/heads/main
```

The resolved commit matches the local `HEAD` and `origin/main` observed during
this verification.

Installation status: `PASS`.

After explicit user authorization, the marketplace was added and the plugin was
installed as `codex-image-factory@partme-ai-image-factory`, version `0.1.0`, with
status `installed, enabled` and authentication policy `ON_USE`.

A fresh `codex exec` session reported all four exact Skill names as discoverable:

- `codex-image-factory-use`
- `codex-image-factory-run`
- `codex-image-factory-judge`
- `codex-image-factory-recover`

The same fresh session confirmed that `bin/image-factory` exists, is executable,
and is reachable from the plugin root. Other configured MCP integrations emitted
startup warnings in that session; they did not prevent Skill discovery or the
CLI check and are not attributed to this plugin.
