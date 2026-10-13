> 2026-10-09 过度设计裁剪：删除治理与评审证据平台范围（规格归档与变更流程 1.x、版本化评审接口 4.x、重复哈希与校准/漂移证据 5.x、人工审阅工作台 6.x、校准比较报告 7.3、归档门禁 8.6、发布证据更新 8.7）；历史见 git。保留功能行：连续性基准、结构化 story state、真实运行/宿主/故障验收与发布交付。未完成行保持实现导向单行。

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

## 7. P2 Runtime acceptance

- [x] 7.1 新增 runtime acceptance matrix schema 和记录命令，状态限定为 PASS/FAIL/BLOCKED/NOT_RUN；初始 11 案例全部 `NOT_RUN`
- [ ] 7.2 执行真实付费 4/8/12 镜头连续性基准并逐图人工标注
- [ ] 7.4 执行 Codex/ZCode/Kimi 可用组合的独立宿主验收，未运行组合保持 NOT_RUN
- [ ] 7.5 执行中断、重复回调、并发、磁盘不足和额度耗尽故障验收

## 8. Release and verification

- [x] 8.1 更新中英文架构、技术方案、生产质量指南、README 和 CHANGELOG
- [x] 8.2 运行目标测试、全量测试、合同迁移、`validate_distribution.py` 和离线 vendor check
- [x] 8.3 运行严格 OpenSpec 全量验证并核对未触碰受管技能与 `skills.lock.json`
- [x] 8.4 按完成阶段 bump minor 版本，同步四份 manifest 与市场 catalog
- [x] 8.5 提交、推送、PR/CI、tag/release、市场同步和已安装 Codex 缓存验收（PR #8、v0.7.0、市场 c64a7f9、缓存 510 tests）
