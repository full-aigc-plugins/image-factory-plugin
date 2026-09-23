## Decisions

1. 每次 attempt 持久化 `attempt_id`、事件 JSONL、进度快照和发现的 session id。
2. 使用 `subprocess.Popen` 并逐行消费 stdout/stderr；事件先落盘，再用于状态分类。
3. 产物归属优先匹配事件中的 session/call 与生成目录结构；全局 diff 只允许一个新候选且没有竞争 attempt。
4. timeout/interrupted 进入 Unknown，并保留 attempt handle；recover 只对该 handle 查找晚到产物和回执。
5. 容量预检采用保守预算并同时检查工作目录、生成目录和目标目录；不自动删除任何数据。
6. `status --watch` 是只读观察，不触发重试或状态跃迁。

## Migration Plan

在 v0.4.0 之上以 TDD 实现，保持历史 ledger 可迁移；完成后发布 v0.5.0。
