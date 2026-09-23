## ADDED Requirements

### Requirement: Runtime reliability SHALL be evidenced by an acceptance matrix

中断恢复、重复回调、并发、磁盘不足和额度耗尽行为 SHALL 可写入运行验收矩阵，且每个结果 SHALL 绑定实际插件版本与证据引用。单元测试通过 MUST NOT 自动产生运行 `PASS`。

#### Scenario: Recovery passes in a unit test only
- **WHEN** 恢复逻辑单元测试通过但未执行真实宿主案例
- **THEN** 真实恢复验收保持 `NOT_RUN`

### Requirement: Concurrent attempts SHALL retain isolated attribution

并发运行验收 SHALL 证明每个产物、事件和恢复句柄只归属一个 attempt；发现跨 attempt 归属时案例 MUST 为 `FAIL`。

#### Scenario: Two jobs finish together
- **WHEN** 两个作业并发产生图片
- **THEN** 每个回执只引用其自身 attempt 的证据且不存在交叉收集
