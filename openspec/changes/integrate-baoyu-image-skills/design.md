## Context

The plugin already vendors reusable skills from immutable releases and declares plugin-only exceptions separately. The selected Baoyu skills form one functional set: `baoyu-cover-image` and `baoyu-xhs-images` resolve an image backend, while `baoyu-image-gen` provides the portable provider and Codex CLI execution layer.

The current Baoyu checkout declares package version `2.5.2` and contains the desired implementation at commit `87866b1e36a67403d9c6f3ee75b4a16482c4f83f`, but the remote repository has not published tag `v2.5.2`. The existing immutable tag `v1.63.0` predates the Codex CLI backend and therefore cannot satisfy the requested capability.

## Goals / Non-Goals

**Goals:**

- Install the three selected Baoyu skills with their complete scripts and references unchanged.
- Make source identity and local content independently verifiable.
- Preserve clear routing between direct creative generation and governed factory batches.
- Support release-driven upgrades from either external skill package.

**Non-Goals:**

- Do not import Baoyu writing, publishing, translation, or article-authoring skills.
- Do not modify Baoyu frontmatter, workflow text, provider code, or defaults.
- Do not merge Image Factory and Video Factory runtimes.
- Do not publish or move a Baoyu tag as part of the plugin-side change.

## Decisions

1. The three skills are one external source entry named `baoyu-skills`; none are added to `plugin-local-skills.json`.
2. The lock targets `v2.5.2` and the exact current commit. Local vendoring may use `--source-path` for development, but release and online checks remain blocked until the immutable remote tag resolves to that same commit.
3. Factory-specific policy tests apply only to `image-factory-*` skills. External skills are instead checked for frontmatter identity, allowed directory layout, source digest, and byte equality. This avoids changing upstream content merely to satisfy local prose conventions.
4. Sync dispatch accepts `package`, `ref`, and `sha`. Omitting `package` preserves backward compatibility by selecting `image-factory-skills`; an explicit package is required for Baoyu upgrades.
5. Direct cover, social-card, and provider generation requests may trigger Baoyu skills. Requests requiring batch approval, receipts, deterministic evaluation, optimization rounds, or recovery remain routed to Image Factory workflows.
6. `image-factory-harness` is the plugin-local capability arbiter. Its entrypoint keeps only fast routing and hard boundaries; a plugin-local capability map holds mixed-mode decisions, normalized delivery evidence, and downstream video handoff fields. It MUST reference external skills by name and MUST NOT duplicate their provider tables, style matrices, or execution workflows.

## Risks / Trade-offs

- [Baoyu `v2.5.2` tag is not yet published] -> offline validation can prove the snapshot, but release and online supply-chain checks stay blocked until the tag exists at the locked commit.
- [Baoyu skills support API-key providers] -> documentation must no longer claim the entire plugin never reads provider credentials; that claim remains true only for the governed Factory runtime.
- [Broader trigger surface] -> descriptions remain upstream-owned, while the README and local harness explain when to use direct Baoyu flows versus the Factory pipeline.
- [A request asks for Baoyu creativity and Factory receipts together] -> the harness discloses that no execution adapter exists and asks the user to choose direct creative generation or governed Factory execution; it never fabricates Factory receipts for a direct run.

## Migration Plan

1. Add the second source entry and vendor the three directories from the local Baoyu checkout.
2. Update inventory, supply-chain tests, workflow dispatch, notices, and user documentation.
3. Run byte-equality, offline vendor, distribution, and full unit tests.
4. Publish immutable Baoyu tag `v2.5.2` at the locked commit, then run the online vendor check.
5. Only after all checks pass, bump and publish Image Factory and update the marketplace catalog without mixing unrelated changes.
