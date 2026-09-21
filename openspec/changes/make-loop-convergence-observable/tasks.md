## 1. Specification

- [x] 1.1 定义 `independent-dimensioned-critique`：评审独立性、命名维度记录、反棘轮、平台边界、无用户面、保持 advisory
- [x] 1.2 定义 `loop-convergence-evidence`：台账数字历史、回归、两级停滞、保持非自主、优雅退化
- [x] 1.3 运行 `openspec validate --strict` 并确认未修改 `immutable-skill-supply-chain` 与 `cross-host-plugin-identity`

## 2. Score document and ledger

- [x] 2.1 在 `schemas/scores.schema.json` 的 `advisoryScore` 增加命名维度与差距陈述，保持总标量为加法变更且语义不变
- [x] 2.2 扩展 `scripts/evaluator.py` 的 advisory 校验：拒绝未知维度名与越界分，未指名可观察证据的维度报成不完整
- [x] 2.3 提升 `schemas/factory_job.schema.json` 的 `schema_version` 并在 `scripts/contract_migrations.py` 加入迁移，在台账根级新增 `numeric_history` 承载每轮数字（不放 `evaluationRecord` 内：该记录每轮被整体替换，历史放里面会被清掉）
- [x] 2.4 让 `evaluate` 把每轮数字写入台账；无 advisory 时显式记录"该轮无数字评测结果"而非编造
- [x] 2.5 更新 `tests/test_contracts.py` 的 schema 契约断言，明确记录本次放宽了哪一处

## 3. Plugin-local review skill and routing

- [x] 3.1 新增插件本地评审技能：独立上下文、命名维度、反棘轮、平台边界，并声明不承担对话面
- [x] 3.2 在 `plugin-local-skills.json` 登记该技能
- [x] 3.3 在**同一次提交**内更新 `tests/test_distribution_extended.py` 的技能精确相等断言与 `tests/test_skills.py` 的 `FACTORY_EXPECTED`
- [x] 3.4 在 `skills/image-factory-harness/SKILL.md` 增加一条按技能名称路由到该技能的路由，不复制其正文
- [x] 3.5 确认 harness 的交付契约把分维度批评记为治理证据，且不把它描述为判词

## 4. Convergence detection

- [x] 4.1 在 `scripts/optimizer.py` 新增回归判定，报告时同时引用两轮证据
- [x] 4.2 新增两级停滞信号（接近 / 已确认）与各自处置：结构性改变，或交给人
- [x] 4.3 保留 `optimizer_missing_instruction` 与轮次上限语义，禁止任何评测信号直接产生一轮
- [x] 4.4 无数字评测时静默退化：不报回归、不报停滞、不阻塞循环

## 5. Verification and evidence

- [x] 5.1 新增测试：因维度评分而需要返工的条目仍被缺少指令闸门拦下
- [x] 5.2 新增测试：反棘轮（变差即允许更低分并报回归）与维度证据完整性
- [x] 5.3 新增测试：advisory 未启用时不出现回归或停滞结论，且轮次上限仍被报成 incomplete
- [x] 5.4 跑通全部单测、`scripts/validate_distribution.py`、`skill_vendor.py check --offline` 与 `FORBIDDEN_PHRASES` 扫描
- [x] 5.5 用一次真实多轮作业刷新 `docs/verification/runtime.md` 的证据表，使收敛声明可由台账核验
- [x] 5.6 确认未触碰 `skills.lock.json`、7 个受管技能目录与 `hooks/`
