## Why

当前每个图片条目都在独立 Codex 子进程中生成。即使人工在每条 prompt 中重复人物描述，计划、批准、回执和返工都不知道哪些人物与元素必须保持一致，也不会自动把相同锚点带入后续帧，导致人物脸型、服装、道具和画风漂移。

## What Changes

- 图片批次可以声明系列一致性档案，包括风格圣经、禁止变化项和实体注册表。
- 实体可以声明类型、固定特征和身份参考图；条目显式列出本帧实体与允许变化。
- 参考图获得 `identity`、`style`、`prop`、`layout`、`edit_target`、`generic` 角色，角色与内容摘要共同绑定生成身份。
- 验证器把一致性档案编译为每个条目的有效 prompt，并把有效 prompt 摘要纳入计划批准、幂等键和回执。
- 优化轮次保留系列档案、实体绑定与锚点引用，避免返工时丢失连续性。

## Capabilities

### New Capabilities

- `series-consistency-contract`: 定义多图批次的实体、风格、参考图角色、有效 prompt 与跨轮次保留规则。

## Impact

影响批次 schema、迁移、计划验证、runner、artifact receipt 语义、optimizer、技能文档和对应测试。旧 1.0.0 至 1.2.0 计划继续安全迁移；没有一致性档案的计划保持原行为。
