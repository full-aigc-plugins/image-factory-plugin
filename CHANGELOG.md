# Changelog

## 0.3.0 — 2026-09-23

- 在 Codex 会话中优先路由到内置 `imagegen` / `image_gen`，默认不要求 Provider API Key。
- 依据当前会话宿主元数据或真实工具能力区分 Codex、ZCode、Kimi 与 unknown，不再根据技能安装状态猜测宿主。
- 仅在结构化图片额度耗尽证据出现后，才向 Codex 用户提供 Baoyu 外部 Provider 降级。
- 锁定并完整捆绑 `image-factory-skills v1.1.0` 的逐字节验证 `imagegen` 快照。
- 修复版本提升脚本，使仓库 marketplace 的 ref/icon 与版本同步，并支持单插件市场生成和校验。

## 0.2.0 — 2026-09-22

### Added

- Loop-convergence evidence: the durable ledger records each round's numeric assessment (`numeric_history`), so "which round scored best" and "did the final round regress" are answerable from the ledger alone.
- Named-dimension critique: advisory entries may carry bounded per-dimension scores with observable evidence; unevidenced dimensions are recorded as incomplete and never count as gaps.
- Regression and two-level stall detection: `optimize` reports regressions with both rounds' evidence, rejects `--retry-unchanged` while a stall is approaching, and stops with `optimizer_stall_established` once a structural rework fails to lift the score. No evaluation signal can open a round.
- Plugin-local `image-factory-review` skill: silent, independent-context, anti-ratchet dimensioned review consumed by `evaluate`; routed by the harness.
- Declared pixel checks: plan items may declare corner-colour, minimum-margin, and ink-colour checks; a standard-library decoder measures them lazily and a failure joins the deterministic tier (`failed_pixel_check`). Checks are carried across rounds unchanged and never enter idempotency keys or receipts.
- Consumed `image-factory-skills` v1.0.2: the judge now requires an independent scoring context and documents the dimensioned advisory and anti-ratchet rule.

### Changed

- `factory_job` ledger schema 1.1.0 → 1.2.0 (adds `numeric_history`; migration chain provided).
- `image_batch` plan schema 1.1.0 → 1.2.0 (adds optional `pixel_checks`); `scores` schema 1.0.0 → 1.1.0 (widens the deterministic failure enum by one member and adds check details).
- Skills sync selects the source-organization token by repository owner.

## 0.1.6 — 2026-09-20

### Changed

- Replaced Codex-first public branding with host-neutral Image Factory identity across documentation and release artwork.
- Kept Codex, ZCode, and Kimi host-specific installation details only where they describe an actual host contract.
- Added a regression gate that rejects obsolete host-prefixed public product naming.

## 0.1.5 — 2026-09-20

### Changed

- Migrated active repository identity and install metadata to `full-aigc-plugins/image-factory-plugin`.
- Pinned the repository-local marketplace to immutable `v0.1.5` sources and assets.
- Kept paid-generation behavior and the historical `0.1.2` runtime evidence unchanged.

## 0.1.4 — 2026-09-20

### Changed

- Locked reusable skills to an immutable release tag, peeled commit SHA, and per-skill digests.
- Declared `image-factory-harness` as plugin-local and added mutation tests for managed and local skill boundaries.
- Updated release dispatch, three-host manifests, and distribution checks without changing paid-generation behavior.

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
- Corrected repository ownership: workbench UI, project state, review experience and video composition belong to PartMe Studio, not Image Factory.
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
