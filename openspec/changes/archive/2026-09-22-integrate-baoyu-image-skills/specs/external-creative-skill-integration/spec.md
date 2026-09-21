# external-creative-skill-integration Specification

## Purpose

Expose selected Baoyu image-generation workflows through Image Factory without modifying upstream skill content, while keeping direct creative generation distinct from the governed Factory batch pipeline.

## Requirements

## ADDED Requirements

### Requirement: Selected Baoyu skills are complete and unchanged

The plugin MUST include `baoyu-image-gen`, `baoyu-cover-image`, and `baoyu-xhs-images` from one exact immutable Baoyu release. Every file in each installed skill directory MUST match the locked upstream source byte-for-byte.

#### Scenario: Plugin is installed without network access

- **WHEN** a host discovers skills from the installed plugin
- **THEN** all three Baoyu skills, their scripts, references, and assets are available locally without a runtime clone

#### Scenario: Managed Baoyu content is edited in the plugin

- **WHEN** any managed Baoyu file differs from its locked upstream digest
- **THEN** the offline vendor check fails and identifies the affected skill

### Requirement: Creative and governed workflows remain distinguishable

The plugin MUST expose direct Baoyu generation for one-shot images, covers, and social card series, while preserving Image Factory workflows for approved batches, receipts, deterministic evaluation, optimization rounds, and recovery.

#### Scenario: User requests a social image-card series

- **WHEN** the request matches the upstream `baoyu-xhs-images` trigger
- **THEN** the host can select that unchanged skill and use its own confirmation and backend-selection workflow

#### Scenario: User requests an auditable production batch

- **WHEN** the request requires plan validation, spend approval, receipts, evaluation, or recovery
- **THEN** the host routes to the `image-factory-*` workflow rather than treating direct Baoyu generation as governed execution

### Requirement: Content writing stays outside Image Factory

The plugin MUST NOT bundle Baoyu article writing, formatting, translation, or publishing skills solely to support the three image workflows.

#### Scenario: Skill inventory is audited

- **WHEN** the locked Baoyu source entry is inspected
- **THEN** it contains exactly the three approved image skills and no content-writing or publishing skill

### Requirement: The plugin-local harness arbitrates without duplicating upstream skills

`image-factory-harness` MUST route direct image, cover, social-card, and governed batch requests to the owning skill by name. Conditional capability detail MUST use a plugin-local reference, and the harness MUST NOT copy upstream provider tables, style matrices, or execution procedures.

#### Scenario: One workflow clearly owns the request

- **WHEN** a request matches direct image generation, article cover, social image cards, or governed batch production
- **THEN** the harness selects `baoyu-image-gen`, `baoyu-cover-image`, `baoyu-xhs-images`, or `image-factory-use` respectively and stops before duplicating the delegated workflow

#### Scenario: Direct creativity and Factory governance are both required

- **WHEN** the request requires a Baoyu creative workflow and Factory approval, receipts, evaluation, or recovery in one execution
- **THEN** the harness states that no execution adapter currently combines them and asks the user to choose the direct or governed path

### Requirement: Every route produces a normalized delivery summary

The harness MUST require a route-neutral completion summary containing the selected skill, execution backend when reported, output paths, prompt records, references, governance evidence, and unverified items. The summary MAY be handed to Video Factory, but MUST NOT claim that Image Factory performed video execution.

#### Scenario: A direct Baoyu workflow completes

- **WHEN** a direct image, cover, or social-card workflow returns artifacts
- **THEN** the summary records its actual skill and backend evidence and marks Factory approval, receipts, and evaluation as not applicable

#### Scenario: A governed Factory batch completes

- **WHEN** Image Factory produces or recovers a batch
- **THEN** the summary cites the actual plan, approval, receipts, evaluation, and unresolved evidence available for that batch
