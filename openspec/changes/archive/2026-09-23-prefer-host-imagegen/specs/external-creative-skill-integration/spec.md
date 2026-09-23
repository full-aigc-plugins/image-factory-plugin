## MODIFIED Requirements

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
