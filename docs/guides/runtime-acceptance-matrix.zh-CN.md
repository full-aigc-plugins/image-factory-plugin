# 真实运行验收矩阵

`data/benchmarks/runtime-acceptance-matrix.json` 记录的是运行证据状态，不是测试通过清单。
本轮仅实现离线记录机制；真实付费 4/8/12、跨宿主/模型/供应商与五类故障注入均为
`NOT_RUN`。synthetic 单元测试只证明算法与合同，不得替代人物、服装、道具连续性的真实验收。

## 记录流程

```bash
bin/image-factory acceptance-init --plugin-version 0.8.0 --out matrix.json --json
bin/image-factory acceptance-add --matrix matrix.json --case model-codex-a \
  --kind model_comparison --host Codex --model observed-model \
  --provider observed-provider --prompt-strategy story-state-v1 --json
bin/image-factory acceptance-record --matrix matrix.json --case paid-4 \
  --record paid-4-record.json --json
```

`acceptance-init` 拒绝覆盖已有矩阵。`acceptance-add` 只增加独立的 `NOT_RUN` 案例。
`acceptance-record` 只记录，不启动生成；`PASS`/`FAIL` 必须声明 `live_runtime`、
起止时间与非空证据引用。矩阵校验拒绝手工把无证据的条目改为 `PASS`。
付费故事 `PASS` 还必须提供 `story_proof`：精确镜头数、已核验回执数、逐帧人工标签数、
付费调用数、回执/标签引用和实际耗时；可观察费用写数值，不可观察写 `null`。
记录器不会验证外部证据文件的真实性，负责人仍需核验回执、费用、原图和逐帧人工标注。

付费基准至少分别运行 4、8、12 镜头，按人物脸型/年龄/发型、服装、书包、书本、灯具、
场景状态逐帧标注，并记录一次通过率、返工轮次、人物漂移率、元素丢失率、实际费用和耗时。
模型/供应商/提示策略须各有独立案例与足够标签，不从一个宿主推断另一个宿主。

故障案例要求 `fault_proof` 同时记录 `duplicate_paid_calls`、
`recovery_handle_preserved`、`artifact_misattributed`、`external_calls`、`final_state`。
磁盘不足只有外部调用为零才能 `PASS`；中断只有恢复句柄保留才能 `PASS`。
额度耗尽、重复回调、并发等同样必须提供可核对的调用轨迹和最终状态。
