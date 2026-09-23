## Why

当前 runner 通过全局生成目录的前后 diff 归属产物，并在 `subprocess.run(capture_output=True)` 返回前不可见进度。并发外部写入可能被误认领，超时后也缺少按会话恢复的直接索引；有限磁盘空间直到复制阶段才暴露。

## What Changes

- 为每次 attempt 创建独立证据目录和事件流文件，绑定 attempt、session、call 与候选产物。
- runner 流式读取 JSONL 事件并原子写入进度快照，提供只读 watch/status。
- 优先按 session/call 归属产物；仅在严格单候选条件下兼容目录 diff。
- 超时或中断保留恢复句柄，recover 只核对同一 attempt，不自动重新生成。
- 运行前估算批次工作空间和目标空间，空间不足在批准后、调用前失败。

## Capabilities

### New Capabilities

- `generation-runtime-reliability`: 定义 attempt 归属、流式进度、容量预检和超时恢复。

## Impact

影响 runner、ledger、CLI status/recover、artifact collector、schema、测试与运维文档。依赖 `series-consistency-contract` 的生成身份，但不改变其语义。
