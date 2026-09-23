# external-creative-skill-integration Specification

## Purpose
Expose selected Baoyu image-generation workflows through Image Factory without modifying upstream skill content, while keeping direct creative generation distinct from the governed Factory batch pipeline.
## Requirements
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

`image-factory-harness` MUST 先依据当前会话证据识别宿主，再把请求按技能名称交接。Codex 的直接生图 MUST 优先选择 `imagegen`；只有明确图片配额耗尽后，Harness 才能把普通图片、封面或社交卡片分别作为可选降级交给 `baoyu-image-gen`、`baoyu-cover-image` 或 `baoyu-xhs-images`。Factory 治理请求继续交给 `image-factory-use`。条件能力细节 MUST 使用插件本地引用，Harness MUST NOT 复制上游 Provider 表、风格矩阵或执行步骤。

#### Scenario: One Codex workflow clearly owns the request

- **WHEN** Codex 用户确认直接生图且内置图片能力可用
- **THEN** Harness 选择 `imagegen` 并停止，不预先进入 Baoyu Provider 或密钥流程

#### Scenario: One workflow clearly owns the request

- **WHEN** 请求明确属于 Factory 治理、非 Codex 原生图片能力，或已满足 Codex 配额降级闸门
- **THEN** Harness 按宿主证据与内容类型选择唯一入口并停止，不复制被交接技能的执行正文

#### Scenario: Codex image quota is explicitly exhausted

- **WHEN** 内置路径提供结构化图片配额耗尽证据
- **THEN** Harness 按请求类型提供最窄的 Baoyu 技能作为可选降级，并保留其自己的确认与配置流程

#### Scenario: Direct creativity and Factory governance are both required

- **WHEN** 请求同时需要外部创作工作流与 Factory approval、receipts、evaluation 或 recovery
- **THEN** Harness 说明当前没有 execution adapter 能组合两者，并要求用户选择直接或治理路径

### Requirement: Every route produces a normalized delivery summary

The harness MUST require a route-neutral completion summary containing the selected skill, execution backend when reported, output paths, prompt records, references, governance evidence, and unverified items. The summary MAY be handed to Video Factory, but MUST NOT claim that Image Factory performed video execution.

#### Scenario: A direct Baoyu workflow completes

- **WHEN** a direct image, cover, or social-card workflow returns artifacts
- **THEN** the summary records its actual skill and backend evidence and marks Factory approval, receipts, and evaluation as not applicable

#### Scenario: A governed Factory batch completes

- **WHEN** Image Factory produces or recovers a batch
- **THEN** the summary cites the actual plan, approval, receipts, evaluation, and unresolved evidence available for that batch

