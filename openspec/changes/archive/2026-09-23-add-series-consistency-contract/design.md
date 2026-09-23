## Context

Factory 的治理强项是批准、回执和收敛，但生成调用彼此独立。连续性必须在调用前被编译成确定输入，而不能依赖会话记忆或 reviewer 事后猜测。

## Decisions

1. 批次 schema 升为 1.3.0，新增可选 `consistency_profile`；旧计划迁移后等价于没有档案。
2. `consistency_profile.entities` 是唯一实体注册表。每个实体拥有稳定 id、类型、描述、固定特征与可选参考图。
3. 每个 item 用 `entity_ids` 选择本帧实体，用 `allowed_variations` 明确本帧可变化内容；未知实体必须在运行前拒绝。
4. 结构化 `references` 为路径赋予角色与可选实体 id。旧 `reference_images` 继续作为 `generic` 角色兼容，但两类引用与档案引用合计不得超过宿主上限 5。
5. 有效 prompt 由纯函数编译，顺序固定：系列规则、风格、负向约束、实体固定特征、允许变化、参考角色、场景请求。路径不写入 prompt，避免机器相关绝对路径污染身份。
6. 幂等键绑定有效 prompt 与按顺序排列的 `(role, entity_id, sha256)`；同一路径换角色属于不同生成请求。
7. `prompt_sha256` 从本版本起表示实际送入 runner 的有效创作 prompt 摘要；无档案时它仍等于作者 prompt 摘要。
8. optimizer 深拷贝顶层一致性档案和条目绑定，返工只替换作者场景 prompt。

## Risks / Trade-offs

- 参考图与提示约束只能提高可控性，不能保证底层模型绝对一致；质量层仍需在后续版本加入逐图对锚评审。
- 五张参考图上限会迫使计划在角色数量和布局参考之间取舍；验证器在花费前明确拒绝超限计划。
- schema 版本提升会增加迁移与文档维护成本，但保持旧计划无损迁移。

## Migration Plan

1. 先写 schema、validator、runner、receipt 与 optimizer 的失败测试。
2. 实现 1.2.0 到 1.3.0 的无损迁移和有效 prompt 编译。
3. 更新技能文档与示例，运行定向和全量回归。
4. 发布 v0.4.0，并把真实宿主连续性效果保留为独立运行验收，不用单测冒充模型效果。
