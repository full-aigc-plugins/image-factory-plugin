## Why

插件能判定产物**是否完好**，却不能判定这个循环**是否在收敛**：唯一的循环出口是轮次上限，而它只被报成 incomplete，并且持久台账对每轮评测只留一个摘要，早期轮次的数字本身没有留存。结果是同一个作业的第 2 轮比第 1 轮更差时无人察觉，循环可以把整个轮次预算花在毫无变化的微调上。

`docs/verification/runtime.md` 记录过一次多轮闭环（`multi_round_closed_loop` PASS），其拒绝依据是仓外算出的像素指标。该证据标准要求"声明必须用非插件自身代码的工具重新推导"，而今天台账只能回答 `decision=fail`，回答不了"第 1 轮的分数是多少"——它指向一个哈希，而那个文件可能已在同一路径被覆写。这处证据缺口与任何外部技能无关，是本变更的直接动机。

## What Changes

- 新增一个**插件本地**评审技能，从一个**独立于**计划与提示词作者上下文的评审过程中产出分维度批评，并把它写入评分文档。
- 扩展评分文档：在每个条目既有的单一总标量之外，增加按命名维度的有界评分与具体差距陈述。总标量保持可比，**既有字段的语义不变**。
- 扩展持久台账：把每轮的**数字**评测结果记入 `evaluationRecord`，而不仅是一个摘要；外部评分文档被覆写后历史仍可读。
- 在优化步骤新增**回归**与**停滞**判定，停滞分两级（approaching / established），对应"还需更大改动"与"交给人"两种处置。
- 明确**不做**：不新增自主循环、不新增用户可见界面、不新增 `target_image` 字段、不编辑任何受外部管理的技能、不改变确定性门与三级权威的排序。

## Capabilities

### New Capabilities

- `independent-dimensioned-critique`: 让某轮的产物由**独立于生成上下文**的评审来打分，并把结果记为**命名维度**而非一个不透明的数；同时保持它是 advisory，永不单独判定失败。包含反棘轮（变差就允许更低分）与"不许承诺平台没有的能力"两条纪律。
- `loop-convergence-evidence`: 让插件能回答"同一作业的连续轮次是否在变好"——靠把每轮的数字评测留在持久台账里，并据此报告回归与停滞，且不因此获得任何自主权。

### Modified Capabilities

无。`immutable-skill-supply-chain` 里"Plugin-local skills are explicit"这条要求本就规定了"插件专属技能必须显式声明"，新增第二个本地技能是在**遵守**它，不是在修改它。`cross-host-plugin-identity` 不受影响。

## Impact

受影响面（全部为插件本地、可编辑）：新增 `skills/<review-skill>/` 并在 `plugin-local-skills.json` 登记；`schemas/scores.schema.json`（advisoryScore 增维度、可选放宽 gate 枚举留待后续变更）；`schemas/factory_job.schema.json`（`evaluationRecord` 增数字历史，含 schema_version 提升）；`scripts/evaluator.py` 的 advisory 校验；`scripts/optimizer.py` 的回归/停滞判定；`scripts/contract_migrations.py` 的迁移；`scripts/image_factory_cli.py` 的 evaluate 参数面；`skills/image-factory-harness/` 增加一条路由；以及四处**必须同步修改的清单与断言**：`tests/test_distribution_extended.py` 的技能精确相等断言、`tests/test_skills.py` 的 `FACTORY_EXPECTED`、`tests/test_contracts.py` 的 schema 契约断言、`docs/verification/runtime.md` 的证据表。

**不触碰**：`skills.lock.json`、7 个受管技能目录（含 `image-factory-judge`）、`hooks/`（两个钩子皆无需改动：SessionStart 环境检查与 UserPromptSubmit 意图提示均为 advisory，视觉/评审门不属于钩子层）。
