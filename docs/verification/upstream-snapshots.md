# Upstream snapshot verification

Recorded 2026-09-13 for the Image Factory prompt-discovery baseline.

## Result

| Source | Revision | Files | Result |
| --- | --- | ---: | --- |
| `freestylefly/awesome-gpt-image-2` | `0dc09c46c8a30b1fdd89c18cc78a894dac2104e3` | 7 | PASS |
| `wuyoscar/GPT-Image2-Skill` | `05cb1130bba29e0fc028220376280a2e934a8041` | 50 | PASS |
| `YouMind-OpenLab/ai-image-prompts-skill` | `6e8339bbfda7ed3f21978df84f266f1c393f5918` | 18 | PASS |
| `YouMind-OpenLab/awesome-gpt-image-2` | `7516ce0d3132231e0de80f8a7978bc6ed728abe5` | 2 | PASS |

Every vendored file was compared with the Git blob SHA from the corresponding
GitHub tree using the Git blob header and file bytes. Total: 77 files checked,
zero mismatches. `vendor/upstream/BLOB_SHA1SUMS` preserves those expected blob
identities, and `tests/test_upstream_snapshot_baseline.py` recomputes them.

The two inspected repositories without a declared license are pointer-only in
`vendor/upstream/sources.json`; no content directory exists for either source.

## Runtime boundary

The snapshots are below `vendor/upstream`, outside `.codex-plugin/plugin.json`'s
active `skills/` path. Four upstream `SKILL.md` files are present as source
material and four Image Factory Skills remain active. Snapshot Markdown is
excluded from product-document model-name and link-resolution checks because it
must remain unchanged; its identity is governed by blob hashes instead.

No upstream installer, API client, automatic update, prompt record, or embedded
tool instruction was executed during import.

## Repository verification

```text
python3 -m unittest discover -s tests -v
Ran 241 tests — OK

python3 scripts/validate_distribution.py .
validated codex-image-factory compatibility foundation 0.1.1
```

This proves snapshot identity, current plugin regression behavior and
distribution structure. It does not prove the visual quality of a future image run.
