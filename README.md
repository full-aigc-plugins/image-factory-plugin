# Codex Image Factory Plugin

<img src="assets/logo.png" alt="Codex Image Factory logo" width="128">

> Batch image production for Codex, with a verified receipt for every artifact.

[English](README.md) | [简体中文](README.zh-CN.md)

## Status

Version 0.1.1 adds attributed offline prompt discovery, pinned upstream Skill snapshots, Creative Studio architecture, and a 72-case Chinese documentation library. The image production core remains runtime-verified; current and historical evidence is recorded under `docs/verification/`.

## Purpose

`codex-image-factory` turns a reference-driven image task into an auditable production run. It validates a batch plan, has Codex generate each item, collects every produced image with a recomputed hash, evaluates the batch against deterministic gates, and turns the failures into a new prompt round that you approve before it runs.

```text
Codex -> validated batch plan -> built-in image tool -> collected artifacts + receipts
                                                              |
                                        deterministic gates + advisory score
                                                              |
                                              optimized prompt round (approved)
```

The plugin never generates images itself. Generation is performed by Codex through its own built-in image tool and your existing Codex authentication.

## Platform boundaries

These are measured properties of the Codex image tool, not preferences. The plugin is built around them.

- The image model used for a batch is chosen by Codex. It is not selectable here, and this repository does not hardcode or promise any model name. Receipts record only what Codex reports, and record `null` when Codex reports nothing.
- The built-in tool accepts only a prompt and reference images. Size, quality, background, and image count are fixed by Codex, so batch items differ only by prompt and reference images.
- One tool call produces one image, and an edit accepts at most five reference images.
- Image generation consumes the usage allowance of the Codex account in use. The plugin estimates the batch, requires approval before running, and never retries automatically.

Because generation is not parameterised, features that require explicit size or quality control are out of scope rather than planned. A plugin-owned API channel would be a separate, clearly marked extension point; this repository does not add one and does not read API keys.

## What the factory adds

- **Batch plan validation** — closed schemas, idempotency keys, and hard caps before anything is spent.
- **Verified receipts** — every hash, size, and dimension is recomputed from the file on disk, with a second check to catch a file rewritten mid-validation.
- **Durable ledger** — atomic writes, a governed state machine, and secret scrubbing, so an interrupted run resumes instead of regenerating.
- **Evaluation** — deterministic gates decide; a model-authored score is advisory, and your approve/reject labels are captured so that score can be calibrated against real decisions.
- **Optimization as a new round** — failures are rewritten into a new prompt set rather than overwriting the previous one.

## Documents

Prompt preparation now includes an offline template search:
`bin/image-factory prompt-search 'storybook illustration' --limit 3 --json`.
See [prompt reference integration](docs/prompt-library.md) for bundled templates,
case indexes, source attribution and the limits of this integration.

- [Architecture](docs/Codex-Image-Factory-Plugin-Architecture.md)
- [架构文档](docs/Codex-Image-Factory-Plugin-Architecture.zh_CN.md)
- [Technical solution](docs/Codex-Image-Factory-Plugin-Technical-Solution.md)
- [技术方案](docs/Codex-Image-Factory-Plugin-Technical-Solution.zh_CN.md)
- [Design specification](docs/superpowers/specs/2026-09-12-codex-image-factory-plugin-design.md)
- [Implementation plan](docs/superpowers/plans/2026-09-12-codex-image-factory-plugin-implementation.md)
- [Portable manifest migration](docs/portable-migration.md)
- [Runtime verification](docs/verification/runtime.md)
- [Upstream Skill capability analysis](docs/upstream-skill-capability-analysis.md)
- [Creative Studio design](docs/superpowers/specs/2026-09-13-codex-creative-studio-design.md)
- [Creative Studio implementation plan](docs/superpowers/plans/2026-09-13-codex-creative-studio-implementation.md)
- [Creative Studio Chinese user guide](docs/guides/creative-studio-user-guide.zh-CN.md)
- [Chinese use-case library](docs/use-cases/README.zh-CN.md)
- [Current CLI recipes in Chinese](docs/guides/current-cli-recipes.zh-CN.md)
- [Original upstream snapshots](vendor/upstream/README.md)
- [Upstream snapshot verification](docs/verification/upstream-snapshots.md)

## License

Apache-2.0 — see [LICENSE](LICENSE).
