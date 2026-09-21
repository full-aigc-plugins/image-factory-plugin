# Image capability map

只有请求跨越多个图片工作流、同时要求直接创作与 Factory 治理，或需要把图片交给
Video Factory 时才读取本文件。普通请求应直接按 `SKILL.md` 的快速路由执行。

## Ownership map

插件已捆绑下列技能，路由时不得重复安装。这里的独立安装命令仅标识外部所有权和
独立消费方式，不应在用户任务中自动执行。

| 能力所有者 | 适用信号 | 执行边界 | 独立安装来源 |
| --- | --- | --- | --- |
| **`baoyu-image-gen`** | 普通生图、参考图、指定 Provider、保存好的多 prompt 批次 | 使用该技能自己的偏好、确认、后端选择和失败处理 | `npx skills add partme-ai/baoyu-skills --skill baoyu-image-gen` |
| **`baoyu-cover-image`** | 文章封面、头图、封面尺寸与视觉维度 | 生成并保存封面 prompt，再由该技能选择的图片后端执行 | `npx skills add partme-ai/baoyu-skills --skill baoyu-cover-image` |
| **`baoyu-xhs-images`** | 小红书、微信图片卡片、社交信息图系列 | 使用该技能自己的策略、确认、锚点链和批次策略 | `npx skills add partme-ai/baoyu-skills --skill baoyu-xhs-images` |
| **`image-factory-use`** | 审批、报价、回执、确定性评测、优化轮次、状态恢复 | 进入 Factory plan / ledger / receipt 状态机 | `npx skills add full-aigc-skills/image-factory-skills --skill image-factory-use` |
| **`image-factory-review`** | Factory 批次内的独立分维度评审、跨轮收敛/回归/停滞证据 | 只产出 advisory 评分文档；不承担对话面，判词仍归 `image-factory-use` 路径 | 插件本地技能，不单独安装 |

## Selection priority

1. 明确的封面信号优先交给 **`baoyu-cover-image`**。
2. 明确的卡片或小红书信号优先交给 **`baoyu-xhs-images`**。
3. 其他直接生图信号交给 **`baoyu-image-gen`**。
4. 只要用户把 approval、receipt、deterministic evaluation 或 recovery 声明为验收条件，
   就不能悄悄走直接路径；按下一节处理。
5. “多张图片”本身不等于 Factory 治理。只有明确需要治理证据，或已有 Factory
   plan / ledger 时，才进入 **`image-factory-use`**。

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
selected_skill: baoyu-image-gen | baoyu-cover-image | baoyu-xhs-images | image-factory-use
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
