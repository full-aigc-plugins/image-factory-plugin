# loop-convergence-evidence Specification

## Purpose
让插件能够回答"同一作业的连续轮次是否在变好"：把每轮的数字评测结果留在持久台账中，并据此报告回归与停滞，使循环的收敛性成为可从台账独立核验的证据，而不是只能靠人回看图片来判断。
## Requirements
### Requirement: The ledger records each round's numeric assessment

持久作业台账 MUST 记录每一轮产出的**数字**评测结果，而不仅是外部评分文档的摘要。记录 MUST 在外部评分文档被覆写或删除后仍然可读，并且 MUST 足以在**不重跑生成、不读取插件自身外部评分文件**的前提下回答"哪一轮最好、最后一轮是否退步"。

#### Scenario: The external scores file is replaced

- **WHEN** 某作业已有两轮评测，且调用方在同一路径覆写了评分文档
- **THEN** 台账仍能报告较早那一轮的数字评测结果

#### Scenario: A round is evaluated without an advisory

- **WHEN** 某一轮在未提供 advisory 的情况下完成评测
- **THEN** 台账记录该轮不存在数字评测结果，且 MUST NOT 为其编造一个值

### Requirement: Regression is reported

当同一作业的后一轮评测结果劣于更早一轮时，插件 MUST 报出**回归**并同时给出来自两轮的证据。回归 MUST NOT 被报成进展，且它本身 MUST NOT 授权开启新一轮。

#### Scenario: Round 2 is worse than round 1

- **WHEN** 第 2 轮的数字评测结果低于第 1 轮
- **THEN** 输出报告一次回归，并引用两轮各自的评测证据

#### Scenario: A regression exists but no decision was made

- **WHEN** 已报出回归，且没有任何条目收到显式指令
- **THEN** 不产生下一轮，既有"需要返工但缺少指令"的失败照常返回

### Requirement: Stall has two graded states

插件 MUST 区分**接近停滞**与**已确认停滞**。接近停滞 MUST 在"最佳估值在两轮内没有提升一个完整档位"或"同一维度连续两轮被点名"时触发，处置是**要求一次结构性改变而非继续微调**；已确认停滞 MUST 在结构性改变之后估值仍未提升时触发，处置是**交给人决定**。

#### Scenario: Two rounds show no full-step improvement

- **WHEN** 同一作业连续两轮的最佳估值提升不足一个完整档位
- **THEN** 报出接近停滞，且下一轮 MUST 由一次结构性改变驱动而非继续小步调整

#### Scenario: An architectural change did not help

- **WHEN** 已按接近停滞的要求做过一次结构性改变，而估值仍未提升
- **THEN** 报出已确认停滞，并把决定交给用户，而 MUST NOT 继续消耗轮次预算尝试其他结构性改动

### Requirement: The loop remains non-autonomous

任何评测信号 MUST NOT 直接产生一轮。每个被标为需要返工的条目 MUST 在产生下一轮之前收到一条显式指令；达到轮次上限 MUST 继续被报成 incomplete，而 MUST NOT 被报成成功。

#### Scenario: A stall or regression signal exists without an instruction

- **WHEN** 已报出停滞或回归，且某个需要返工的条目既无改写也无显式保留重试
- **THEN** 返回既有的缺少指令失败，且不产生下一轮

#### Scenario: The round ceiling is reached

- **WHEN** 下一轮将超出计划声明的轮次上限
- **THEN** 结果仍被报成 incomplete 并留待人工决定，停滞与回归的判定不得把它改成成功

### Requirement: Convergence analysis degrades gracefully

当批次不存在数字评测结果时，插件 MUST NOT 报出回归或停滞，也 MUST NOT 因此阻塞循环。

#### Scenario: Advisory is disabled

- **WHEN** 某一轮在 advisory 未启用的情况下完成评测
- **THEN** 输出中不出现任何回归或停滞结论

#### Scenario: Advisory is disabled and the ceiling is reached

- **WHEN** 在无数字评测结果的情况下达到轮次上限
- **THEN** 轮次上限仍是唯一被报出的限制，且输出中不含停滞或回归结论

