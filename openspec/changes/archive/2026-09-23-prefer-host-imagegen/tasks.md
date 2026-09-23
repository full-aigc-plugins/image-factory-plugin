## 1. Contract and failing tests

- [x] 1.1 定义宿主证据、Codex 内置优先与严格配额降级边界
- [x] 1.2 增加 Harness 路由测试并确认旧实现失败

## 2. Harness implementation

- [x] 2.1 修改 Harness 主路由与 Mermaid 图
- [x] 2.2 修改能力地图，增加宿主识别与失败分类矩阵
- [x] 2.3 明确密钥只在用户选择 Baoyu 后由用户本地配置

## 3. Managed skill integration

- [x] 3.1 在源技能包发布后把 `imagegen` 加入不可变 lock
- [x] 3.2 用 vendor 工具复制完整快照并校验摘要
- [x] 3.3 更新三个宿主的技能发现/分发断言

## 4. Verification and publication boundary

- [x] 4.1 运行全量单测、分发校验与离线 vendor check
- [x] 4.2 运行两仓 `openspec validate --strict`
- [x] 4.3 记录在线 remote/tag 校验与真实三宿主加载仍待发布
