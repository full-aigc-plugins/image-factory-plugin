---
name: image-factory-harness
description: Image Factory calling spec — the bin/image-factory CLI surface with probe, prompt-search, validate-plan, quote, run, evaluate, optimize, recover and status subcommands, generation-dir vs destination separation, budget gates and the reject-optimize-rerun loop. Note the platform chooses model, size and quality. Use when generating any image.
---

# 图片工厂调用规范

## When to use

执行任何出图任务之前——先读本规范再动 CLI。它定义调用纪律与计费门禁；
具体工作流的技能细节在 image-factory-run / judge / recover 各自技能里。

**依赖披露（事实，不是缺陷）**：CLI 底层经**本地 Codex CLI** 出图，消耗的是
**Codex 账户的图片配额**，生成模型由 Codex 平台选择（不可通过参数指定）——模型、size 与 quality 均不可控。
需要本机已安装 Codex CLI。

## Workflow

执行通道：`<插件根>/bin/image-factory`（shell 入口）；所有命令支持 `--json`
取机器可读输出。

1. `probe` 确认环境可用；不可用就停，报探测输出。
2. `prompt-search` 找提示词基线 → 写 plan → `bin/image-factory validate-plan <plan>`
   → `bin/image-factory quote <plan>`。
3. `bin/image-factory run <plan>` → `bin/image-factory evaluate <产物>`：
   主色/留白/构图按计划阈值判定，不过就走优化闭环。
4. 交付时列出：计划参数、产物路径、评测数值、消耗与剩余配额、未验证项。

## Never do

- **`--generation-dir` 与 `--destination` 分离**：plan/job 工作目录不得放进 destination 产物树。
- destination 以外不落正式产物；quote 超预算就不 run，如实上报。
- 每一步的 JSON 输出是事实来源；叙述与 JSON 冲突时以 JSON 为准。
- 配额是硬约束：任何"再试一次"之前先看 `quote`/`status`。
