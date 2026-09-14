# Changelog

## Unreleased

## 0.1.2 — 2026-09-14

### Added

- Plan-bound approval: every generation round records the plan hash, the round, and
  the number of remaining generation calls, and a rewritten round or a partially
  finished batch requires a fresh approval for exactly the work that is left.
- Cross-process job locking, so a second `run` is refused with `job_already_running`
  instead of independently deciding the same item is still pending.
- An explicit attempt lifecycle (`Attempting`, `Generated`, `Failed`, `Unknown`), with
  the attempt reserved before the external call so an interruption cannot spend twice.
- Per-item receipts written atomically under their idempotency key, with the aggregate
  manifest derived by verifying those receipts against the artifacts they name.
- `recover`, which reconciles interrupted items from receipts already on disk, rebuilds
  the manifest, and never makes a generation call.
- Schema version 1.1.0 with deterministic migration from 1.0.0 for image plans and job
  ledgers; a legacy job that already carries approval evidence is refused rather than
  migrated, because its binding cannot be reconstructed.
- A cross-platform CI workflow running the suite on Ubuntu, macOS, and Windows with
  Python 3.11 and 3.13, installing nothing.

### Changed

- Human result labels are mandatory: an unlabeled batch reaches `pending_approval`
  instead of passing on its own, and a human rejection fails the batch regardless of
  any advisory score.
- The job state machine no longer lets a settled, completed, or unresolved job return
  directly to `Running`; such transitions are rejected and reconciled by `recover`.
- `optimize` requires `--job` and refuses scores that are not the ones the job recorded.
- `status` reports the plan, approval, per-state counts, evaluation, and optimization
  without disclosing prompts, reference paths, or environment paths.

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
