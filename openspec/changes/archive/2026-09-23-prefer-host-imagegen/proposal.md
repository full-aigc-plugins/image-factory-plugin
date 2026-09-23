## Why

当前 Harness 把普通生图、封面和社交卡片无条件交给 Baoyu，因此 Codex 用户即使已有无需 API Key 的内置生图能力，也会过早进入 Provider 选择和密钥配置。插件又同时支持 Codex、ZCode 与 Kimi，不能靠已安装技能名称猜测宿主。

## What Changes

- Harness 先依据当前会话的可靠宿主元数据与工具能力识别 Codex、ZCode、Kimi 或 unknown。
- Codex 中所有已确认的直接生图优先交给系统 `imagegen` 与内置 `image_gen`。
- 只有内置路径明确返回图片配额耗尽证据时，才向用户提供 Baoyu 三个技能作为可选降级，并说明本地配置对应 Provider 密钥。
- 缺工具、鉴权失败、网络失败、超时和一般生成失败不得伪装成额度耗尽。
- Factory 治理批次继续走 `image-factory-use`；其 `quota_exceeded` 台账可作为同样的降级证据，但 Baoyu 结果不得伪造 Factory 回执。

## Capabilities

### New Capabilities

- `host-aware-image-routing`: 按宿主能力选择内置生图或外部 Provider，并限制 Codex 降级条件。

### Modified Capabilities

- `external-creative-skill-integration`: Baoyu 从 Codex 默认路径改为配额耗尽后的可选降级；非 Codex 宿主按其真实原生能力或外部 Provider 路由。
- `immutable-skill-supply-chain`: 消费新增的上游 `imagegen` 快照时仍需不可变 tag、peeled SHA 与摘要。

## Impact

影响插件本地 Harness、能力地图、路由测试、受管技能锁与技能清单。不会修改任何已锁定的受管技能正文；正式上游 tag 与远端锁验证需在源技能包发布后完成。
