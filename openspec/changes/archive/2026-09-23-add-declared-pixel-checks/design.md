## Context

`docs/verification/runtime.md` 的 0.1.2 与 1.2.0 两次真实记录中，唯一的拒绝依据都是计划里写下的可度量要求（白底、边距 19.5%→23.3%、墨色 green_adv +28），而这些度量至今在仓外完成——`artifact_collector.parse_png_size` 只读 24 字节头，全仓无解码能力。同时 `test_contracts.py` 对五元失败枚举做精确等值断言，`make-loop-convergence-observable` 的 design 已把"枚举放宽"显式留作后续变更的合法口子。

## Goals / Non-Goals

**Goals:**

- 标准库 PNG 解码（覆盖 Codex 生图实际产出的形态），惰性解码（仅声明了检查的条目）。
- 三种封闭检查（角点色/最小边距/墨色均值），声明进计划、失败进确定性层、明细进加法字段。
- 跨轮不可削弱：改写只动 prompt，checks 随行深拷贝（既有 optimizer 行为天然满足，规格化）。

**Non-Goals:**

- 不做通用视觉断言（布局、语义、美学）——那是评审技能的 advisory 层。
- 不做第三方图像库、不做 16 位/隔行/Adam7 支持——不支持形态 fail-closed。
- 不改幂等键、回执模式与五门既有语义；不放钩子层。

## Decisions

1. **解码器独立成 `png_pixels.py`，检查求值独立成 `declared_checks.py`**：evaluator 保持薄门；两模块均可独立测试。
2. **枚举放宽恰好一项 `failed_pixel_check`**：五个既有枚举各有一个真值，像素检查同样只有一个真值，因此进同一层而不是另立权威；明细（kind/measured/expected）放 `gateResult.pixel_checks` 加法字段，旧行不含该字段。
3. **`image_batch` 升 1.2.0**：新增可选 `batchItem.pixel_checks`（≤8 条，结构封闭），迁移链 1.0.0→1.1.0→1.2.0，1.1.0→1.2.0 为带注记的透传（旧文档天然合法）。
4. **参数校验在 `plan_validator`（代码侧）而非 schema**：`schema_lite` 无 oneOf/if-then，按 kind 的必填参数与取值范围由代码校验，schema 只约束结构封闭。
5. **fail-closed**：不支持形态、解码异常一律记为该检查失败并注明原因——"测不了"绝不等价于"通过"。
6. **性能护栏**：解码只发生在声明了检查的条目上；200 张无声明批次的评测路径与今日完全相同。

## Risks / Trade-offs

- [纯 Python 解码大图较慢] → 仅声明检查的条目解码；典型批次（个位数条目）在秒级。
- [检查写错导致好图被判失败] → 检查是人声明的判据，与"声明的边距不够"同性质；明细记录 measured/expected 供人复核，改写与重开批次均可修正声明。
- [枚举放宽破坏既有消费者] → 仅新增一个成员，既有五成员语义不变；`test_contracts` 同步放宽并留注记。
- [模型借改写削弱检查] → 结构性不可能：optimizer 对行深拷贝且改写仅替换 prompt，规格已固化此性质。

## Migration Plan

1. 本变更规格先行，不动代码。
2. `png_pixels.py` + `declared_checks.py` 落地并单测（各滤镜/色彩类型的手工 PNG）。
3. schema 1.2.0 + 迁移链 + scores 枚举放宽（contracts 测试同批放宽并记录）。
4. PlanItem/plan_validator 解析与校验；evaluator 门内接入（惰性）。
5. 真实产物零花费实证：对 `.evidence` 中第 1/2 轮的两张真实生成图声明白底检查，前者必须失败、后者必须通过。
6. 全套测试 + 分发校验 + vendor 校验。
