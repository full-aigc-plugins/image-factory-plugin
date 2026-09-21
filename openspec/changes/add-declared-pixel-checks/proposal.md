## Why

插件今天只能回答产物"是否完好"（存在、是 PNG、够大、哈希一致、无重复），回答不了"是否符合计划里写下的可度量要求"。`docs/verification/runtime.md` 两次记录了同一类真实拒绝：依据是白底、边距、墨色这类**写在计划声明里、可用像素度量**的要求，但这些度量都在仓外手工完成，插件自身连一个像素都解码不了（`parse_png_size` 只读 24 字节头）。结果每一轮这样的偏差都要消耗一次人工拒绝与一轮返工。

## What Changes

- 新增标准库 PNG 解码模块（无第三方依赖），支持本插件生成路径实际产出的 PNG 形态；不支持的形态（隔行、16 位）显式失败，绝不静默通过。
- 计划条目可声明**像素检查**（角点颜色容差、最小边距占比、墨色均值容差三种，各有唯一真值）。检查是人写在计划里的判据，不是模型发明；改写只动 prompt 与参考图，检查跨轮**结构上不可削弱**。
- 评分文档的确定性失败枚举放宽一项（`failed_pixel_check`），检查明细（kind/measured/expected）记录在各自的加法字段里——五个既有枚举的语义不变。
- 声明的检查失败进入确定性层：与其他五门同等权威，直接判定失败，无需人工拒绝。
- 未声明检查的条目完全不解码、不检查、无新失败——对既有批次零行为变化。

## Capabilities

### New Capabilities

- `declared-pixel-checks`: 把计划里声明的可度量要求变成确定性门：人声明、码度量、失败即判，跨轮不可削弱，未声明则完全不介入。

### Modified Capabilities

无。既有能力（供应链、跨宿主身份、维度批评、收敛证据）的行为要求不受影响；评分枚举放宽落在 schema 契约层，由本能力的规格约束。

## Impact

受影响面（全部插件本地）：新增 `scripts/png_pixels.py`（解码与度量）；`scripts/plan_validator.py`（PlanItem 携带 checks + 解析校验）；`schemas/image_batch.schema.json`（版本 1.2.0，`batchItem.pixel_checks`）；`scripts/contract_migrations.py`（image_batch 1.1.0 → 1.2.0）；`schemas/scores.schema.json`（枚举放宽 + `pixel_checks` 明细字段）；`scripts/evaluator.py`（门内惰性解码与检查）；`tests/test_contracts.py`（枚举精确断言同步放宽并记录）；新增 `tests/test_pixels.py`。`optimizer.py` 无需改动（行深拷贝天然携带 checks 且改写不可触碰）。既有五门、advisory 维度、台账数字历史均不变。
