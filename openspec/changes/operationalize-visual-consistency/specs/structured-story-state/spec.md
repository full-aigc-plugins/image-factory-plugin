## Purpose

把故事连续性从重复自然语言升级为可验证状态：稳定属性被锁定，镜头差异被显式声明，未声明状态按确定规则继承，并进入实际生成提示词。

## ADDED Requirements

### Requirement: Story state SHALL separate lock scopes from variables

故事状态 SHALL 区分永久锁定、场次锁定、镜头变量和状态转换。每个状态路径 MUST 在其作用域内唯一，锁定路径 MUST NOT 同时声明为镜头变量。

#### Scenario: A hairstyle is both locked and variable
- **WHEN** 档案把同一发型路径同时放入永久锁定和镜头变量
- **THEN** 计划在报价、批准或生成之前验证失败

### Requirement: Undeclared state SHALL inherit deterministically

第一镜头 SHALL 从档案初始状态开始；后续镜头 SHALL 从前一镜头继承未声明变化的状态。状态转换 MUST 指明路径、旧值和新值，旧值与继承值不一致时计划验证失败。

#### Scenario: A closed book becomes open
- **WHEN** 后续镜头声明书本状态从 `closed` 转为 `open`
- **THEN** 编译状态只改变该路径，并保留人物、服装和其他场景状态

### Requirement: Effective prompts SHALL materialize resolved state

每个镜头的有效提示词 SHALL 包含解析后的永久锁定、当前场次锁定、当前镜头状态和本镜头状态转换。相同档案和状态序列 MUST 产生字节一致的状态片段。

#### Scenario: Two unchanged frames share locked identity
- **WHEN** 两个连续镜头没有声明人物身份变化
- **THEN** 两个有效提示词包含完全相同的人物锁定状态片段

### Requirement: Rework SHALL preserve story history

返工计划 SHALL 保留原始状态档案、前序状态和已经批准的转换；改写场景文字 MUST NOT 静默改变锁定属性或新增状态变化。

#### Scenario: A frame is rewritten for composition
- **WHEN** 优化步骤只改写构图要求
- **THEN** 下一轮的解析故事状态与上一轮该镜头一致
