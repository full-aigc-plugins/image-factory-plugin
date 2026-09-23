## 1. Specification and governance

- [x] 1.1 归档 `add-declared-pixel-checks` 并同步 `declared-pixel-checks` 主规格
- [x] 1.2 归档 `make-loop-convergence-observable` 并同步独立评审与收敛主规格
- [x] 1.3 创建本变更 proposal、八组 delta specs、架构设计和分阶段任务
- [x] 1.4 运行 `openspec validate operationalize-visual-consistency --strict` 并修正全部问题

## 2. P0 Foundation — continuity benchmark

- [x] 2.1 先写失败测试，覆盖 4/8/12 镜头约束、证据层级、缺失标签分母和单样本不足
- [x] 2.2 新增 benchmark pack、run 和 report schema，未知成本/耗时只允许 `null`
- [x] 2.3 实现确定性聚合器：一次通过率、返工轮次、人物漂移、元素丢失、成本、耗时和三维分层
- [x] 2.4 添加“勤能补拙”4/8/12 镜头 synthetic 基准清单，明确它们不是 live acceptance
- [x] 2.5 接入 CLI 的离线 benchmark summarize 命令，不调用生成、不修改台账

## 3. P0 Foundation — structured story state

- [x] 3.1 先写失败测试，覆盖锁定/变量冲突、旧值不匹配、未知场次、继承和确定性 prompt
- [x] 3.2 升级 `image_batch` schema，加入永久锁定、场次锁定、变量初值和条目状态转换
- [x] 3.3 实现线性状态解析与有效提示词编译，确保幂等键绑定解析后的状态
- [x] 3.4 保留 story state 跨优化轮次，场景改写不得改变状态合同
- [x] 3.5 增加旧版本合同迁移，禁止为旧计划编造 story state

## 4. P0 Foundation — versioned reviewer interface

- [x] 4.1 先写失败测试，覆盖缺少版本、未知能力、越界分数/置信度、低置信度与人工权威
- [x] 4.2 新增版本化 reviewer report schema 和标准库适配器
- [x] 4.3 让 evaluate 可读取 reviewer report 并保留 reviewer id/version/capability provenance
- [x] 4.4 扩展 scores 合同以无损记录来源、置信度、uncertain 和证据区域
- [x] 4.5 验证评审器信号始终为 advisory，无法成为确定性失败或推翻人工决定

## 5. P1 Evidence — duplicate, calibration and drift

- [x] 5.1 为 aHash/dHash/pHash 组合先写差异图、裁剪和误报回归测试
- [x] 5.2 增加版本化多哈希策略与逐算法距离证据，保留 aHash 兼容模式
- [x] 5.3 为样本充足性、Wilson 置信区间、分层统计和 reviewer drift 写失败测试
- [x] 5.4 扩展校准 schema/实现；样本不足不产生可采纳阈值，漂移不自动改阈值

## 6. P1 Evidence — human review workspace

- [x] 6.1 扩展 storyboard 索引：基准帧、证据区域、来源、分歧和人工标签
- [x] 6.2 增加基准/当前并排、维度筛选、差异标记与人工理由录入
- [ ] 6.3 添加 390x884、768x1024、1280x1024 布局检查与静态安全测试（静态与转义测试已通过；浏览器访问本地页被策略阻止，真实三档渲染仍未验收）
- [x] 6.4 证明审片页仍可从已核验回执重建且不复制原图、不调用模型、不修改台账

## 7. P2 Runtime acceptance

- [x] 7.1 新增 runtime acceptance matrix schema 和记录命令，状态限定为 PASS/FAIL/BLOCKED/NOT_RUN；初始 11 案例全部 `NOT_RUN`
- [ ] 7.2 执行真实付费 4/8/12 镜头连续性基准并逐图人工标注
- [ ] 7.3 分模型、供应商和提示策略运行足够样本，生成可校准比较报告
- [ ] 7.4 执行 Codex/ZCode/Kimi 可用组合的独立宿主验收，未运行组合保持 NOT_RUN
- [ ] 7.5 执行中断、重复回调、并发、磁盘不足和额度耗尽故障验收

## 8. Release and verification

- [x] 8.1 更新中英文架构、技术方案、生产质量指南、README 和 CHANGELOG
- [x] 8.2 运行目标测试、全量测试、合同迁移、`validate_distribution.py` 和离线 vendor check
- [x] 8.3 运行严格 OpenSpec 全量验证并核对未触碰受管技能与 `skills.lock.json`
- [x] 8.4 按完成阶段 bump minor 版本，同步四份 manifest 与市场 catalog
- [x] 8.5 提交、推送、PR/CI、tag/release、市场同步和已安装 Codex 缓存验收（PR #8、v0.7.0、市场 c64a7f9、缓存 510 tests）
- [ ] 8.6 只有全部 P0/P1/P2 证据完成后才归档本 change；任何 live 缺口继续保持未完成
- [ ] 8.7 发布 0.8.0 P1 证据与矩阵更新；核对 PR/CI、市场版本和安装缓存，不改变 P2 `NOT_RUN`
