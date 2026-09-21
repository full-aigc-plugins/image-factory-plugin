## Purpose

把计划里声明的可度量要求（背景色、边距、墨色）变成与其他确定性门同等权威的检查：由人在计划中声明、由标准库代码度量、失败即判，并且跨轮不可被削弱；未声明的条目完全不介入。

## ADDED Requirements

### Requirement: Checks are declared in the plan, not invented

像素检查 MUST 且只能来自计划条目的声明字段。每个声明 MUST 是三种封闭检查之一（角点颜色容差、最小边距占比、墨色均值容差），参数 MUST 在封闭范围内。任何在计划之外生成、推断或补充检查的行为 MUST NOT 发生。

#### Scenario: A plan declares a corner-colour check

- **WHEN** 某条目声明了角点颜色检查及其容差
- **THEN** 评测按该声明度量产物并在评分文档中记录 kind、measured 与 expected

#### Scenario: A rewrite cannot weaken a check

- **WHEN** 优化步骤为下一轮改写某条目的提示词
- **THEN** 该条目的像素检查随行携带且与上一轮完全一致

### Requirement: Undeclared items are untouched

未声明像素检查的条目 MUST NOT 被解码、MUST NOT 产生像素类失败，其评分文档行 MUST 不含像素检查明细。检查的解码 MUST 只发生在声明了检查的条目上。

#### Scenario: A batch without declarations

- **WHEN** 一个批次的所有条目都未声明像素检查
- **THEN** 其评测结果与不存在本能力时的结果逐字段一致

### Requirement: A declared check has one true answer

每种检查 MUST 满足：给定产物像素与声明参数，通过与否存在唯一真值。检查失败 MUST 记入确定性失败（与既有五门同层），MUST 同时记录实测值与声明值。解码器不支持的 PNG 形态 MUST 按检查失败处理（fail-closed），MUST NOT 被记为通过。

#### Scenario: Declared white background measured against black

- **WHEN** 条目声明四角为白色，而产物四角实测为黑色
- **THEN** 该条目产生确定性失败，decision 为 fail，明细含实测 RGB 与声明 RGB

#### Scenario: An interlaced PNG cannot pass silently

- **WHEN** 声明了检查的条目产物是解码器不支持的隔行 PNG
- **THEN** 该检查记为失败并注明原因，而不是被跳过或记为通过

### Requirement: Receipt semantics are unchanged

像素检查是评测判据，MUST NOT 进入幂等键、回执或生成输入。同一提示词与参考图在增删检查前后 MUST 产生相同的幂等键，回执的字段集 MUST 保持不变。

#### Scenario: Adding a check does not change generation identity

- **WHEN** 同一条目仅增删像素检查后重新验证计划
- **THEN** 其幂等键与计划哈希的构成规则不变，回执模式无新增字段
