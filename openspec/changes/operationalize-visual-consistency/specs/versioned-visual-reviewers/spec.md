## Purpose

用统一、版本化且可追溯的报告接入人物相似度、服装、道具、OCR 和人体结构评审器，同时记录置信度与分歧并保持所有视觉判断为 advisory。

## ADDED Requirements

### Requirement: Reviewer reports SHALL identify their producer and capabilities

每份标准评审报告 SHALL 声明评审器 id、版本、能力集合、输入批次和轮次。能力集合 SHALL 使用封闭名称；无法观察的模型或供应商字段 MUST 为 `null`，不得推断。

#### Scenario: Reviewer version is missing
- **WHEN** 调用方提交一份标准评审报告但未声明版本
- **THEN** 适配器拒绝该报告而不是把版本写成未知字符串

### Requirement: Reviewer findings SHALL carry confidence and evidence

每条发现 SHALL 包含维度、分数、置信度、可观察证据和可选证据区域。不确定度达到声明阈值时 SHALL 标为 `uncertain`，不得单独驱动返工。

#### Scenario: Face similarity is low confidence
- **WHEN** 身份评审器给出低相似度但置信度低于策略阈值
- **THEN** 该发现被保留为不确定证据并请求人工复核，而不是自动失败

### Requirement: Multiple reviewers SHALL expose disagreement

同一镜头同一维度存在多个评审器时，系统 SHALL 保留各原始发现并计算一致、分歧或证据不足状态。系统 MUST NOT 通过挑选最高或最低分隐藏分歧。

#### Scenario: Two wardrobe reviewers disagree
- **WHEN** 两个版本化评审器对服装连续性给出相反结论
- **THEN** 汇总结果标记 reviewer disagreement 并保留两份来源

### Requirement: Reviewer authority SHALL remain advisory

标准评审报告、embedding、OCR、grounding 和人体结构信号 MUST NOT 成为确定性文件失败，也 MUST NOT 推翻人工拒绝或人工批准。

#### Scenario: All reviewers approve a human-rejected frame
- **WHEN** 所有视觉评审器给出高分但人工标签为拒绝
- **THEN** 人工决定保持权威，评审器结果仅作为校准证据
