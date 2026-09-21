## 1. Specification

- [x] 1.1 定义 `declared-pixel-checks`：声明封闭、跨轮不可削弱、未声明不介入、唯一真值、fail-closed、回执语义不变
- [x] 1.2 `openspec validate --strict` 通过且既有能力零修改

## 2. Decode and evaluate

- [x] 2.1 `scripts/png_pixels.py`：标准库解码（ctype 0/2/3/4/6、8 位、非隔行）+ 角点/边距/墨色度量
- [x] 2.2 `scripts/declared_checks.py`：三种封闭检查求值，输出 kind/passed/measured/expected
- [x] 2.3 `tests/test_pixels.py`：手工 PNG（滤镜 0-4、多色彩类型）解码正确性、三检查通过/失败、fail-closed

## 3. Plan and schema

- [x] 3.1 `schemas/image_batch.schema.json` 升 1.2.0 并加 `batchItem.pixel_checks`（≤8、结构封闭）
- [x] 3.2 `contract_migrations.migrate_image_batch` 接受 1.2.0（1.1.0→1.2.0 带注记透传）
- [x] 3.3 `plan_validator`：PlanItem 携带 checks、按 kind 校验参数、检查不入幂等键
- [x] 3.4 `schemas/scores.schema.json`：枚举加 `failed_pixel_check`、`gateResult.pixel_checks` 明细字段
- [x] 3.5 `tests/test_contracts.py`：枚举精确断言放宽为六元并记录、新增 pixel_checks/schema 1.2.0 断言

## 4. Gate integration

- [x] 4.1 `evaluator._gate` 惰性接入：有声明才解码；失败进枚举、明细进行；无声明逐字段等价
- [x] 4.2 optimizer 无需改动：验证 next_plan 深拷贝携带 checks 且改写不可触碰（测试固化）

## 5. Verification and evidence

- [x] 5.1 真实产物零花费实证：`.evidence` 第 1 轮黑底图声明白底必须失败、第 2 轮白底图必须通过
- [x] 5.2 全套单测 + `validate_distribution` + vendor 离线校验 + `openspec validate --strict`
- [x] 5.3 确认未触碰受管技能、`hooks/`、`skills.lock.json`
