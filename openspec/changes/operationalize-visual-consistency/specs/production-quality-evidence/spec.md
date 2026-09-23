## ADDED Requirements

### Requirement: Perceptual duplicate evidence SHALL be algorithm-versioned

近重复证据 SHALL 记录所用算法集合、各算法距离和策略版本。现有 `average-hash-8x8-luma-v1` 行为 SHALL 保持兼容；启用组合策略时 SHALL 使用声明的 aHash、dHash、pHash 规则，不得把结果称为人物身份判断。

#### Scenario: A crop evades average hash
- **WHEN** 组合策略发现 aHash 未命中但其他声明算法达到近重复条件
- **THEN** 报告记录每个算法距离和最终组合判定

### Requirement: Calibration SHALL expose sample sufficiency and intervals

校准报告 SHALL 声明最小样本量、实际样本量、样本是否充分以及误报/漏报指标的置信区间。样本不足时 SHALL 保留原始统计但不得提出可采纳阈值。

#### Scenario: Only one human label exists
- **WHEN** 某分层只有一个人工标签且低于最小样本量
- **THEN** 该分层标为样本不足并且不产生可采纳阈值建议

### Requirement: Calibration SHALL stratify and detect drift

当运行元数据可用时，校准 SHALL 按模型、供应商、画风和镜头类型分层，并把当前评审器版本与已批准基线比较。漂移信号 SHALL 只触发复核，不得自动修改阈值。

#### Scenario: A reviewer upgrade raises false positives
- **WHEN** 新评审器版本相对基线的误报率超出声明容差
- **THEN** 报告标记漂移并保持现有阈值不变
