## Why

Image Factory currently exposes only its governed batch-production workflow. The Baoyu image skills already provide direct multi-provider image generation, article-cover composition, and social image-card workflows, including the Codex CLI image backend that motivated this integration. Reimplementing or editing those skills inside the plugin would create a divergent fork and blur ownership.

## What Changes

- Add `baoyu-image-gen`, `baoyu-cover-image`, and `baoyu-xhs-images` as externally managed, checksummed skills.
- Preserve every upstream file byte-for-byte; Image Factory owns only the lock, routing boundary, documentation, and release metadata.
- Keep `image-factory-harness` as the only plugin-local skill and retain the existing governed batch workflow.
- Generalize the skill-sync workflow so a release event identifies which locked package is being upgraded.
- Document the boundary between direct Baoyu creative workflows and Image Factory's approval/receipt/evaluation pipeline.

## Capabilities

### New Capabilities

- `external-creative-skill-integration`: exposes unchanged Baoyu image workflows from the installed plugin while retaining immutable source provenance.

### Modified Capabilities

- `immutable-skill-supply-chain`: upgrade events select an exact locked package when a plugin consumes more than one external skill repository.

## Impact

This change affects `skills.lock.json`, the vendored skill tree, sync workflow, skill inventory tests, manifests, notices, and bilingual README files. It does not change the three Baoyu skill implementations or move content-writing skills into Image Factory. Video Factory remains the owner of video execution and composition.
