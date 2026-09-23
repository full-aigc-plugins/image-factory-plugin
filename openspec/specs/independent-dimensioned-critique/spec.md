# independent-dimensioned-critique Specification

## Purpose
让某一轮的产物由一个**独立于生成过程**的评审来评估，并把结论记录为若干**命名维度**而不是一个不透明的数字，从而让"哪里还不够"可以被下游明确取用，同时保持它始终是 advisory、永不单独决定批次成败。
## Requirements
### Requirement: Critique is independent of the generating context

插件 MUST 由一个独立于计划与提示词作者上下文的评审过程产出分维度批评。该评审 MUST 只接收本轮产物、本轮明确声明的要求，以及上一轮批评（若存在）；它 MUST NOT 接收生成过程的对话记录，也 MUST NOT 被要求为自身产出的产物评分。

#### Scenario: A round is reviewed

- **WHEN** 某一轮的产物进入分维度评审
- **THEN** 评审的输入集合包含产物、本轮声明的要求与上一轮批评，且不包含生成对话记录

#### Scenario: The plugin-local review skill is inspected

- **WHEN** 检查产出该批评的插件本地技能文档
- **THEN** 它要求评审在独立上下文中完成，且不含"对你自己生成的产物打分"这类指令

### Requirement: Critique is recorded per named dimension

插件 MUST 把批评记录为一组**命名维度的有界评分**加上一个总值。每个维度 MUST 附带一条指名可观察证据的差距陈述；只有笼统印象、未指名任何可观察证据的维度 MUST 被报成不完整，而 MUST NOT 被计为一个差距。

#### Scenario: A critique is recorded

- **WHEN** 一个条目的分维度批评写入评分文档
- **THEN** 文档同时包含各维度的评分与总值，且总值仍与既往轮次可比

#### Scenario: A dimension names no observable evidence

- **WHEN** 某个维度的陈述只给出笼统印象而未指名可观察证据
- **THEN** 该维度被报成不完整，且不计为差距

### Requirement: Critique MUST NOT ratchet

记录的估值 MUST 允许在当轮比既往轮次更差时下降。评审 MUST NOT 被要求达到或超过既往估值，且估值的下降 MUST 被保留并报成**回归**，MUST NOT 被上调以维持单调。

#### Scenario: The current round is worse

- **WHEN** 当轮的产物明显劣于上一轮
- **THEN** 记录的总值低于上一轮，且该下降被报成回归而非进展

#### Scenario: A prior critique exists

- **WHEN** 为某一轮提供上一轮的批评与估值作为评审输入
- **THEN** 评审被要求保持判断一致，但 MUST NOT 被要求匹配或提高上一轮的估值

### Requirement: Critique MUST NOT promise capability the platform lacks

批评 MUST 只描述产物之间可观察的差异。它 MUST NOT 记录一条补救措施依赖于插件无法控制的生成参数（尺寸、质量、背景、张数、模型）的差距，并且 MUST NOT 表述为一种不需要显式指令就会发生的重试。

#### Scenario: A gap requires an unavailable generation setting

- **WHEN** 某条差距的补救方式要求修改插件无法控制的生成参数
- **THEN** 该条不作为可执行的差距记录

#### Scenario: The review text is inspected

- **WHEN** 检查评审相关的技能文档与记录格式
- **THEN** 其中不含依赖不可用参数的补救建议，也不含绕过显式指令的重试表述

### Requirement: Critique MUST NOT add a user-facing surface

分维度批评 MUST 保持为供优化步骤消费的机器产物。它 MUST NOT 引入新的对话界面，轮次结果的用户可见陈述 MUST 继续由既有判词工作流及其单一对话契约承担。

#### Scenario: A reviewed round is presented to the user

- **WHEN** 一轮已完成评审并可向用户陈述
- **THEN** 该陈述仍由既有判词工作流的对话契约产生，且该契约的内容未被本能力改写

#### Scenario: The plugin-local review skill claims a surface

- **WHEN** 检查插件本地评审技能文档
- **THEN** 它不声明拥有对话界面，且以技能名称交接而非复制他方正文

### Requirement: Critique remains advisory

分维度批评 MUST 仍是 advisory。它 MUST NOT 单独使批次失败、MUST NOT 推翻人工拒绝，且 MUST NOT 被描述为判词。其存在不得改变确定性门与人工标签既有的权威排序。

#### Scenario: Only a critique is available

- **WHEN** 所有确定性门通过、无人工作出拒绝，且仅存在分维度批评
- **THEN** 批次决定不会仅因该批评而成为 `fail`

#### Scenario: A human rejection exists alongside a perfect critique

- **WHEN** 某条目已记录人工拒绝，而其分维度批评全项满分
- **THEN** 批次仍然失败，人工决定继续高于批评

