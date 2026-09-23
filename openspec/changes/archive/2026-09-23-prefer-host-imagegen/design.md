## Context

插件在三个宿主分发，但 Codex 内置 `image_gen` 是宿主专属能力。复制后的 `imagegen` 也会随插件出现在其他宿主，因此“发现技能目录”不是可靠身份信号。现有 Factory runner 已将图片额度耗尽分类为 `quota_exceeded`，并能记录 `limit_id=image_gen` 与 reset time；这比解析自然语言错误可靠。

## Decisions

1. 宿主识别证据顺序为：会话显式宿主元数据，其次是当前会话实际暴露的宿主专属工具；绝不使用技能目录、安装路径或文案猜测。
2. Codex 直接生图统一由 `imagegen` 先接手，封面与卡片技能只在明确配额耗尽后作为用户可选的创作降级。Harness 不复制这些技能的执行正文。
3. 降级闸门只接受结构化配额事件，或 Factory 台账中的 `error_category=quota_exceeded` 且 `usage_limit.limit_id=image_gen`。其他失败停在原路径并如实报告。
4. Baoyu 降级不自动执行。先说明需要哪个 Provider 的本地环境变量/配置，让用户选择并在本机配置；不得要求把密钥贴进对话。
5. ZCode/Kimi 优先使用当前会话真实暴露的原生图片能力。若没有可验证的原生能力，才把 Baoyu 作为外部 Provider 路径；这不是 Codex 的配额降级语义。
6. Factory 治理仍保持独立。降级后的 Baoyu 产物没有 Factory approval、receipt、evaluation 或 recovery 证据。

## Risks / Trade-offs

- 宿主不提供显式元数据且工具清单不完整时会得到 unknown；此时必须报告无法自动判定，而不是误调用 Codex 专属路径。
- 用户可能把普通错误描述成“额度没了”；没有结构化证据时不能自动降级，但可以让用户选择是否改走外部 Provider。
- 源技能包未发布前，插件只能完成本地候选集成，不能声称远端不可变锁已验证。

## Migration Plan

1. 先增加路由契约测试，确认旧 Harness 失败。
2. 修改 Harness 与能力地图，实现宿主识别和严格配额闸门。
3. 源技能包发布后用 vendor 工具更新 `imagegen` 受管快照和锁。
4. 运行全量测试、分发校验、离线与在线供应链校验，再提升插件版本并发布。
