# Image capability map

用户确认要生图后读取本文件，用 current-session 证据识别宿主；请求跨越多个图片工作流、
同时要求直接创作与 Factory 治理，或需要把图片交给 Video Factory 时也读取本文件。

## Host detection

按以下证据顺序识别当前宿主：

1. 当前会话提供的显式宿主元数据；
2. 当前会话实际暴露的宿主专属工具，例如 Codex 的内置 `image_gen`；
3. 两者都没有时标记为 `unknown`，报告无法自动判定，不猜测。

不得根据已安装技能、`imagegen` 目录、插件命名空间、文件路径、环境里的其他 CLI，或
说明文字推断宿主。复制后的 `imagegen` 可能同时出现在 Codex、ZCode 和 Kimi；它的存在
不是 Codex 证据。

## Ownership map

插件已捆绑下列技能，路由时不得重复安装。这里的独立安装命令仅标识外部所有权和
独立消费方式，不应在用户任务中自动执行。

| 能力所有者 | 适用信号 | 执行边界 | 独立安装来源 |
| --- | --- | --- | --- |
| **`imagegen`** | Codex 会话已确认的直接生图或编辑，且暴露内置 `image_gen` | 默认使用宿主内置图片工具，不要求 `OPENAI_API_KEY` | `npx skills add full-aigc-skills/image-factory-skills --skill imagegen` |
| **`baoyu-image-gen`** | 非 Codex 无原生能力，或 Codex 图片额度明确耗尽后的普通图降级 | 使用该技能自己的偏好、确认、后端选择和失败处理 | `npx skills add partme-ai/baoyu-skills --skill baoyu-image-gen` |
| **`baoyu-cover-image`** | 非 Codex 无原生能力，或 Codex 图片额度明确耗尽后的封面降级 | 生成并保存封面 prompt，再由该技能选择的图片后端执行 | `npx skills add partme-ai/baoyu-skills --skill baoyu-cover-image` |
| **`baoyu-xhs-images`** | 非 Codex 无原生能力，或 Codex 图片额度明确耗尽后的社交卡片降级 | 使用该技能自己的策略、确认、锚点链和批次策略 | `npx skills add partme-ai/baoyu-skills --skill baoyu-xhs-images` |
| **`image-factory-use`** | 审批、报价、回执、确定性评测、优化轮次、状态恢复 | 进入 Factory plan / ledger / receipt 状态机 | `npx skills add full-aigc-skills/image-factory-skills --skill image-factory-use` |
| **`image-factory-review`** | Factory 批次内的独立分维度评审、跨轮收敛/回归/停滞证据 | 只产出 advisory 评分文档；不承担对话面，判词仍归 `image-factory-use` 路径 | 插件本地技能，不单独安装 |

## Selection priority

1. Codex 且当前会话有 `image_gen` 时，普通图、封面、卡片和参考图都优先交给
   **`imagegen`**；内容类型不会越过宿主优先级。
2. 只要用户把 approval、receipt、deterministic evaluation 或 recovery 声明为验收条件，
   就不能悄悄走直接路径；按下一节处理。
3. “多张图片”本身不等于 Factory 治理。只有明确需要治理证据，或已有 Factory
   plan / ledger 时，才进入 **`image-factory-use`**。
4. Codex 内置路径明确额度耗尽且用户选择降级后，封面交给 **`baoyu-cover-image`**，
   卡片或小红书交给 **`baoyu-xhs-images`**，其他请求交给 **`baoyu-image-gen`**。
5. ZCode、Kimi 或其他宿主若提供真实原生图片工具，优先使用该工具；否则才进入第 4 条的
   内容类型选择。不得把此路径描述成 Codex 配额降级。

## Codex quota fallback gate

自动提出 Baoyu 降级必须满足以下任一结构化证据：

- 当前 Codex 内置工具明确返回图片额度耗尽事件；或
- Factory 台账同时包含 `error_category=quota_exceeded` 与
  `usage_limit.limit_id=image_gen`。

以下类别都不是额度耗尽，禁止自动进入 Baoyu 密钥流程：

| 失败类别 | 处理 |
| --- | --- |
| `tool_unavailable` | 报告当前会话没有可验证的内置工具，不推断额度 |
| `authentication` | 报告 Codex 登录/权限问题，不改走外部 Provider |
| `network` | 报告网络问题，不改写为额度问题 |
| `timeout` | 报告状态不确定，按原路径恢复或重试决策 |
| `unknown` 或普通生成失败 | 保留原错误，不自动降级 |

用户选择 Baoyu 后，才按所选技能说明配置 Provider。要求用户在**本机**设置对应环境变量
或配置文件；不得粘贴密钥到对话，也不得代用户保存密钥。配置完成前不执行外部调用。

## Mixed requests

当前插件没有把 Baoyu 执行包装进 Factory 状态机的 execution adapter。遇到“使用
Baoyu 封面/卡片能力，同时必须取得 Factory 回执或可恢复台账”时，给用户两个真实选项：

1. **Direct creative path**：保留 Baoyu 的完整创作流程、后端和输出结构；Factory
   `governance_evidence` 标记为 `not_applicable`。
2. **Governed Factory path**：使用 Factory 支持的 prompt + reference_images 计划模型；
   获得批准、回执、评测和恢复能力，但不宣称执行了 Baoyu 的完整封面或卡片工作流。

不要依次运行两个路径来伪造组合。用户选择后，只继续所选路径；另一条记录为未执行。

## Normalized delivery contract

这是交付摘要，不是新的运行时 schema。字段可以用 Markdown 或 JSON 表达，但语义保持一致：

```yaml
detected_host: codex | zcode | kimi | other | unknown
selected_skill: imagegen | baoyu-image-gen | baoyu-cover-image | baoyu-xhs-images | image-factory-use
execution_backend: <实际报告的后端，未知则 unknown>
output_paths:
  - <实际存在的产物路径>
prompt_records:
  - <保存的 prompt 或 plan 路径；没有则 not_available>
reference_inputs:
  - <实际使用的参考输入；没有则 []>
governance_evidence:
  approval: <证据路径、状态或 not_applicable>
  receipts: <证据路径、状态或 not_applicable>
  evaluation: <证据路径、状态或 not_applicable>
  recovery_state: <状态或 not_applicable>
unverified_items:
  - <尚未验证的事实；没有则 []>
```

不得从 prompt、文件名或旧日志推测 `execution_backend`。Factory 路径以 JSON、ledger、
receipt 和 evaluation 文件为准；直接路径以所选 Baoyu 技能及其实际工具输出为准。
`image-factory-review` 产出的分维度批评计入 `governance_evidence` 的 `evaluation`
一项；它是 advisory 证据，不是判词，不得在摘要中表述为批次结论。

## Video Factory handoff

图片工作流完成后，可以把统一摘要作为 Video Factory 的 handoff 输入，并额外补充：

- 图片的叙事顺序与用途，例如封面、镜头参考、角色参考、背景或结尾卡；
- 已知的宽高比、分辨率和时长意图；未知值明确写 `unknown`；
- 哪些图片可以裁切、动画化或重新生成，哪些必须保持身份与构图；
- 用户已经批准的视觉方向，以及仍需视频阶段确认的选择。

Image Factory Harness does not execute video；也不执行剪辑、配音或合成。Video Factory 必须根据
自己的能力、审批和证据契约重新预检，不能把图片阶段的批准自动扩展到视频阶段。
