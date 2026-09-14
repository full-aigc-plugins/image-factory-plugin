# Changelog

## 0.1.2 — 2026-09-14

### Added

- Bound every allowance-spending run to an explicit approval for the exact validated plan hash, round, and remaining image count, with append-only approval history.
- Added cross-process job locking, pre-call `Attempting` lifecycle records, unique attempt identifiers, and refusal of ambiguous automatic retries.
- Made atomic per-item receipts the recovery source of truth and added deterministic reconciliation and aggregate-manifest rebuilding.
- Enforced required human labels before acceptance, with governed evaluation, pending-approval, optimization, and terminal state transitions.
- Added deterministic 1.0.0-to-1.1.0 plan and job schema migration.
- Added a dependency-free CI matrix for Linux, macOS, and Windows on Python 3.11 and 3.13, plus distribution and release-evidence gates.
- Added `docs/guides/runtime-evidence-collection.md`, the procedure for the two release gates that need a human observer, together with the host sandbox and path-placement conditions that decide whether generation can run at all.

### Changed

- Added one shared conversational confirmation contract across the use, run, judge and recover Skills; Codex conversation is the product surface.
- Added compact creation cards, direction choices, per-round generation approval, numbered result labels and plain-language recovery behavior.
- Corrected repository ownership: workbench UI, project state, review experience and video composition belong to PartMe Studio, not Codex Image Factory.
- Retained 68 image generation, editing and review cases; moved the four local-video cases to the PartMe Studio product specification.

### Removed

- Removed the workbench design, workbench implementation plan and workbench user guide from this plugin repository.
- Removed the local-video roadmap from Image Factory documentation.

## 0.1.1 — 2026-09-13

### Added

- Offline `prompt-search` with 22 attributed structured templates and category matches.
- Four byte-preserved upstream Agent Skill snapshots plus one licensed gallery snapshot, all pinned and integrity-tested outside the active Skill inventory.
- Source and license registry for six prompt repositories; two sources without declared licenses remain pointer-only.
- Creative Studio product architecture and a 17-task implementation plan for guided image creation, reference consistency and local story video.
- Chinese user guide, current CLI recipes and 72 actionable use cases across stories, social content, commerce, posters, infographics, publishing, characters, UI, games, editing, review and video.
- Regression tests for prompt search, snapshot identity and complete use-case coverage.

### Changed

- The run Skill can consult prompt-preparation guidance when a batch goal has no plan.
- Product-document validation now treats inactive upstream snapshots as source material governed by blob identity rather than active plugin documentation.
- Third-party notices record bundled snapshots, licenses and pointer-only sources.

### Boundaries

- The graphical Creative Studio, Creative Director automation, derived image formats and local video renderer are designed but not implemented in this release.
- Image generation continues through Codex's built-in image tool and existing account authentication.
- No external generation API, API key, automatic retry or automatic upstream update was added.

## 0.1.0 — 2026-09-12

- Initial batch-plan validation, explicit approval, Codex image orchestration, artifact receipts, durable ledger, deterministic evaluation, optimization, recovery, plugin packaging and runtime evidence.
