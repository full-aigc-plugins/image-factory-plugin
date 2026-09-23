## Purpose

用可重复的 4/8/12 镜头故事组和人工真值衡量人物、服装、道具与场景状态连续性，并让不同模型、供应商和提示策略的结果可比较而不夸大单次成功。

## ADDED Requirements

### Requirement: Benchmark packs SHALL declare coverage and evidence tier

每个基准包 SHALL 声明镜头数为 4、8 或 12，覆盖的人物视角、距离、遮挡、昼夜和情绪条件，以及证据层级 `synthetic` 或 `live`。`synthetic` 运行 MUST NOT 被表述为真实模型连续性验收。

#### Scenario: A synthetic four-shot fixture passes
- **WHEN** 一个使用合成 PNG 的四镜头基准完成全部合同检查
- **THEN** 报告把它标为 `synthetic`，且不产生真实模型已验收的声明

### Requirement: Human truth SHALL be dimensioned and observable

基准 SHALL 对人物身份、发型、年龄、服装、核心道具和场景状态分别记录人工标签，并为拒绝项指名可观察证据。缺少标签的维度 SHALL 进入未标注计数而不是自动视为通过。

#### Scenario: Prop continuity is not labeled
- **WHEN** 某镜头没有核心道具人工标签
- **THEN** 道具指标的分母排除该镜头并报告未标注数量

### Requirement: Benchmark reports SHALL expose operational metrics

每次运行 SHALL 记录一次通过率、返工轮次、人物漂移率、元素丢失率、成本和耗时；不可观察的成本或耗时 MUST 为 `null`，不得写成零。聚合结果 SHALL 按模型、供应商和提示策略分层，并保留运行样本数。

#### Scenario: Provider cost is unavailable
- **WHEN** 宿主未报告某次运行成本
- **THEN** 报告将成本记为 `null`，并仍保留该运行的其他指标

### Requirement: A single run SHALL NOT establish general performance

少于声明最小样本量的分层结果 SHALL 标为 `insufficient_sample`。系统 MUST NOT 从单次成功推导模型、供应商或提示策略的稳定性结论。

#### Scenario: One run scores perfectly
- **WHEN** 某模型仅有一个基准运行且全部镜头通过
- **THEN** 该分层仍标为 `insufficient_sample`，不发布总体稳定率结论
