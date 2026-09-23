## Why

Image Factory 0.6.0 已能记录人物、服装、道具和场景状态的评审证据，但这些证据还没有建立在可重复的真实连续性基准、结构化故事状态和版本化评审器之上。当前系统能回答“这一轮记录了什么”，仍不能可靠回答“跨模型、供应商与提示策略，人物和元素到底稳定了多少”。

本变更把视觉连续性从零散提示词经验推进为可复现、可校准、可人工复核、可跨版本比较的生产能力，并保留概率评审永远低于确定性文件事实和人工决定的权威边界。

## What Changes

- 建立 4/8/12 镜头连续故事基准合同，记录人物漂移、元素丢失、一次通过、返工轮次、成本、耗时，并按模型、供应商、提示策略分层比较。
- 把一致性档案扩展为结构化故事状态：永久锁定、场次锁定、镜头变量和显式状态转换；prompt compiler 继承未改变状态，只注入声明过的差异。
- 新增版本化视觉评审器报告与适配层，支持身份、服装、道具、OCR、人体结构等能力声明、置信度、不确定度和多评审器分歧，同时保持 advisory。
- 把近重复检测升级为版本化多哈希证据，保留现有 aHash 兼容行为，并明确它不等价于人物身份判断。
- 扩展校准报告：最小样本量、置信区间、按模型/画风/镜头类型分层、版本趋势和漂移信号；阈值仍不得自动改变。
- 强化可重建审片工作区：基准帧对照、局部证据、差异标记、失败维度筛选和 390px 移动端布局。
- 增加真实运行与故障验收清单，覆盖跨宿主/模型、付费调用、中断恢复、并发、磁盘和额度边界；未运行的验收必须保持 `NOT_RUN`。
- 归档已经完成的 `add-declared-pixel-checks` 与 `make-loop-convergence-observable`，让 OpenSpec 活跃列表只保留真实未完成工作。

## Capabilities

### New Capabilities

- `continuity-benchmark-evidence`: 定义连续故事基准集、运行记录、人工标签、分层指标和真实/合成证据边界。
- `structured-story-state`: 定义永久锁定、场次锁定、镜头变量、状态转换、继承规则以及有效提示词编译行为。
- `versioned-visual-reviewers`: 定义评审器身份、版本、能力、置信度、不确定度、适配与多评审器分歧语义。
- `human-review-workspace`: 定义可重建、可筛选、适合桌面与 390px 移动端的人工审片证据面。
- `runtime-acceptance-matrix`: 定义真实生成、跨宿主/模型与故障注入的验收记录和 `NOT_RUN` 边界。

### Modified Capabilities

- `series-consistency-contract`: 系列档案从固定 traits 扩展到结构化故事状态和显式状态转换。
- `production-quality-evidence`: 增加版本化多哈希、分层校准、置信区间和漂移证据，但不改变 advisory 权威。
- `generation-runtime-reliability`: 把并发、磁盘、额度与中断场景纳入可记录的运行验收矩阵，而不是仅作为单元测试结论。

## Impact

主要影响 `schemas/` 中的批次、评审、基准与校准合同，`scripts/plan_validator.py`、`evaluator.py`、`calibration.py`、`visual_summary.py`、CLI 参数面和合同迁移，以及对应单元/集成测试与中文使用指南。第一阶段只落地本地、确定性和可合成验证的 P0 基础，不调用付费模型；真实图像基准与跨宿主验收必须在后续任务中产生独立运行证据。

本变更不编辑 `skills.lock.json` 或受外部管理的技能，不把 embedding、OCR、grounding 或解剖检测提升为确定性失败，也不自动调整阈值、自动重试或绕过人工决定。
