## Purpose

用结构化矩阵记录真实生成、跨宿主/模型和故障注入的运行验收，使单元测试、合成验证与生产证据不再被混为同一层级。

## ADDED Requirements

### Requirement: Every runtime case SHALL have an explicit evidence status

运行验收案例 SHALL 使用 `PASS`、`FAIL`、`BLOCKED` 或 `NOT_RUN`，并记录宿主、插件版本、模型/供应商（若观察到）、开始结束时间和证据引用。缺失运行证据 MUST 保持 `NOT_RUN`。

#### Scenario: Paid generation is skipped
- **WHEN** 本轮未执行付费生成
- **THEN** 对应案例为 `NOT_RUN`，不得由合成测试结果替代

### Requirement: Cross-host claims SHALL be host-specific

某一宿主或模型的通过 SHALL NOT 自动推广到其他宿主或模型。矩阵 SHALL 为每个组合保留独立状态和证据。

#### Scenario: Codex passes but Kimi is untested
- **WHEN** Codex 案例通过且 Kimi 未执行
- **THEN** Codex 为 `PASS`，Kimi 保持 `NOT_RUN`

### Requirement: Fault cases SHALL prove bounded behavior

中断、重复回调、并发、磁盘不足和额度耗尽案例 SHALL 记录是否发生重复收费调用、是否保留恢复句柄、是否错误归属产物以及最终状态。

#### Scenario: Disk preflight fails
- **WHEN** 可用空间低于声明预算
- **THEN** 案例只有在确认零次外部生成调用后才能标为 `PASS`
