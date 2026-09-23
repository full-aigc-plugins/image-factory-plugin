## Purpose

让 Image Factory 在当前会话中可靠识别宿主能力，在 Codex 中默认使用内置生图，并把外部 Provider 降级限制到可证明的额度耗尽场景。

## ADDED Requirements

### Requirement: Host detection uses current-session evidence

Harness MUST 使用当前会话的显式宿主元数据或实际工具能力识别 Codex、ZCode、Kimi 或 unknown。它 MUST NOT 根据已安装技能、插件目录或文件路径推断宿主。

#### Scenario: The copied imagegen skill is visible in Kimi

- **WHEN** Kimi 安装插件并发现 `imagegen`
- **THEN** Harness 不因技能存在而把当前会话判定为 Codex

### Requirement: Codex prefers the built-in imagegen path

用户确认要生图后，只要当前会话可靠识别为 Codex 且暴露内置 `image_gen`，Harness MUST 优先交给 `imagegen`，并且 MUST NOT 先要求外部 Provider 密钥。

#### Scenario: A Codex user confirms a direct image

- **WHEN** Codex 会话暴露内置图片工具且用户确认生成
- **THEN** Harness 选择 `imagegen`，不选择任一 Baoyu 技能

### Requirement: Codex fallback requires explicit quota evidence

Harness MUST 只在 Codex 内置路径明确返回图片配额耗尽证据后，才提供 Baoyu 降级。缺工具、鉴权失败、网络失败、超时、普通生成失败和未知错误 MUST NOT 被当成额度耗尽。

#### Scenario: The built-in tool reports a generic failure

- **WHEN** Codex 内置图片工具失败但没有结构化配额耗尽证据
- **THEN** Harness 如实报告失败并停留在 Codex 路径，不提示配置 Baoyu 密钥

#### Scenario: The Factory ledger records image quota exhaustion

- **WHEN** 台账记录 `error_category=quota_exceeded` 且 `usage_limit.limit_id=image_gen`
- **THEN** Harness 可以提供与请求类型匹配的 Baoyu 技能作为用户可选降级

### Requirement: Provider credentials remain user-controlled

选择 Baoyu 降级时，Harness MUST 说明所选 Provider 所需的本地配置，MUST NOT 要求用户在对话中粘贴密钥，且 MUST NOT 在用户选择并完成配置前自动执行。

#### Scenario: The user accepts a Baoyu fallback

- **WHEN** 用户在明确配额耗尽后选择外部 Provider
- **THEN** Harness 指向对应 Baoyu 技能的配置流程，并等待用户在本机完成密钥配置

### Requirement: Governance evidence remains route-specific

Factory 批次转为 Baoyu 降级后，交付摘要 MUST 把 Factory approval、receipt、evaluation 与 recovery 标记为不适用或未完成，不得为外部 Provider 产物伪造治理证据。

#### Scenario: A quota-blocked governed batch uses an external provider

- **WHEN** 用户明确选择 Baoyu 继续生成
- **THEN** 交付摘要记录真实 Baoyu 后端与产物，同时不声称该产物已进入 Factory 回执链
